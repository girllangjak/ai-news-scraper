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
    """AI 요약 로직 (에러 분석 기능 강화)"""
    if not CONFIG["GEMINI_API_KEY"]: return "🔑 API 키 미등록"
    
    # [핵심 수정] 가장 표준적인 v1 경로와 모델명 사용
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": f"뉴스 제목 '{title}'을 한국어 한 문장으로 요약해줘."}]}]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        res = response.json()
        
        # 성공적으로 답변을 받았을 때
        if 'candidates' in res:
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # 실패 시 구글이 보낸 에러 메시지를 직접 확인
        error_info = res.get('error', {}).get('message', '구조 오류')
        return f"⚠️ 실패: {error_info[:20]}"
    except Exception as e:
        return f"⚠️ 통신오류: {str(e)[:15]}"

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
                    # 기사마다 요약을 즉시 실행
                    summary = get_ai_summary(title)
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
    
    if not news_list:
        content.append("뉴스를 찾지 못했습니다.")
    else:
        for i, news in enumerate(news_list, 1):
            content.append(f"[{i}] {news['title']}")
            content.append(f"📝 요약: {news['summary']}")
            content.append(f"🔗 링크: {news['link']}\n")
    
    msg = MIMEMultipart()
    msg['From'], msg['To'] = CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [AI 뉴스] {today} - {topic}"
    msg.attach(MIMEText("\n".join(content), 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
    print("✅ 완료")
