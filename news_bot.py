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
    """GitHub 이슈에서 주제 가져오기 (GH_TOKEN 필수)"""
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        return res[0]['title'] if res and isinstance(res, list) else "오늘의 주요 뉴스"
    except: return "오늘의 주요 뉴스"

def get_ai_summary(title):
    """AI 요약 (가장 안정적인 v1beta 경로)"""
    if not CONFIG["GEMINI_API_KEY"]: return "API 키 확인 필요"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    headers = {'Content-Type': 'application/json'}
    prompt = f"이 뉴스 제목을 한국어 한 문장으로 핵심만 요약해줘: {title}"
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        res = response.json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "요약 생성 실패 (API 응답 오류)"

def fetch_refined_news(query):
    """정밀 검색: 제목에 검색어가 포함된 뉴스만 추출"""
    # 검색어 정교화: 이란 전쟁 -> '이란'과 '전쟁'이 모두 포함되도록
    search_query = f"{query} -광고 -홍보"
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(search_query)}&display=20&sort=sim"
    headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
    
    try:
        items = requests.get(url, headers=headers, timeout=10).json().get('items', [])
        results, seen = [], set()

        for item in items:
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
            
            # [정교화 로직] 검색어의 핵심 단어가 제목에 포함된 경우만 수집
            if any(word in title for word in query.split()):
                fingerprint = title.replace(" ", "")[:10]
                if fingerprint not in seen:
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
        content.append(f"'{topic}' 관련 핵심 뉴스를 찾지 못했습니다. 주제를 '중동 정세' 등으로 바꿔보세요.")
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
    print("✅ 발송 성공")
