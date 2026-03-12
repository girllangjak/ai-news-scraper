import requests
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 1. 설정 관리
CONFIG = {
    "NAVER_ID": os.environ.get("NAVER_ID"),
    "NAVER_SECRET": os.environ.get("NAVER_SECRET"),
    "GMAIL_USER": os.environ.get("GMAIL_USER"),
    "GMAIL_PW": os.environ.get("GMAIL_PW"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"),
    "REPO": "girllangjak/ai-news-scraper",
    "FINAL_COUNT": 5,
}

def get_target_topic():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        return res[0]['title'] if res and isinstance(res, list) else "오늘의 주요 뉴스"
    except: return "오늘의 주요 뉴스"

def get_ai_summary(title):
    """AI 요약 및 에러 상세 메시지 추출"""
    if not CONFIG["GEMINI_API_KEY"]: return "에러: GEMINI_API_KEY가 금고(Secrets)에 없습니다."
    
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": f"뉴스 제목 '{title}'을 한국어 한 문장으로 요약해줘."}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        res = response.json()
        
        # 1. 성공 시 요약 결과 반환
        if 'candidates' in res and len(res['candidates']) > 0:
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # 2. 실패 시 구글이 보낸 에러 메시지를 메일에 그대로 노출
        if 'error' in res:
            return f"❌ AI 서버 응답 에러: {res['error'].get('message', '알 수 없는 메시지')}"
        
        return f"❌ 알 수 없는 응답 구조: {str(res)[:100]}..."
    except Exception as e:
        return f"❌ 통신 중 장애 발생: {str(e)}"

def fetch_refined_news(query):
    search_query = f"{query} -광고 -홍보"
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(search_query)}&display=20&sort=sim"
    headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
    
    try:
        items = requests.get(url, headers=headers, timeout=10).json().get('items', [])
        results, seen = [], set()
        for item in items:
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
            if any(word in title for word in query.split()):
                fingerprint = title.replace(" ", "")[:10]
                if fingerprint not in seen:
                    summary = get_ai_summary(title) # 여기서 에러가 나면 상세 사유를 가져옴
                    results.append({"title": title, "link": item['link'], "summary": summary})
                    seen.add(fingerprint)
            if len(results) >= CONFIG['FINAL_COUNT']: break
        return results
    except: return []

if __name__ == "__main__":
    topic = get_target_topic()
    news_list = fetch_refined_news(topic)
    today = datetime.now().strftime('%Y-%m-%d')
    
    content = [f"🤖 AI 분석 리포트: {topic}\n", "="*50]
    for i, news in enumerate(news_list, 1):
        content.append(f"[{i}] {news['title']}")
        content.append(f"📝 요약: {news['summary']}") # 이 부분에 에러 내용이 찍힙니다.
        content.append(f"🔗 링크: {news['link']}\n")
    
    msg = MIMEMultipart()
    msg['From'], msg['To'] = CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [AI 뉴스 테스트] {today} - {topic}"
    msg.attach(MIMEText("\n".join(content), 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
    print("✅ 발송 시도 완료")
