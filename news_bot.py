import requests
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

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
        return res[0]['title'] if isinstance(res, list) and len(res) > 0 else "오늘의 주요 뉴스"
    except: return "오늘의 주요 뉴스"

def get_ai_summary(title):
    # 직접 확인하신 최신 모델 적용
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": f"뉴스 제목 '{title}'을 한국어 한 문장으로 핵심만 요약해줘."}]}]}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        res = response.json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return "요약 생성 중 오류"

def fetch_news(query):
    # 검색어를 조금 더 넓게 잡습니다 (유연한 검색)
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(query)}&display=30&sort=sim"
    headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
    try:
        items = requests.get(url, headers=headers, timeout=10).json().get('items', [])
        results, seen = [], set()
        for item in items:
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
            # 중복 제거 및 수집
            fingerprint = title.replace(" ", "")[:12]
            if fingerprint not in seen:
                summary = get_ai_summary(title)
                results.append({"title": title, "link": item['link'], "summary": summary})
                seen.add(fingerprint)
            if len(results) >= CONFIG['FINAL_COUNT']: break
        return results
    except: return []

if __name__ == "__main__":
    topic = get_target_topic()
    news_list = fetch_news(topic)
    today = datetime.now().strftime('%Y-%m-%d')
    
    content = [f"🗞️ AI 분석 리포트: {topic}", "="*50 + "\n"]
    if not news_list:
        content.append(f"'{topic}'에 대한 검색 결과가 없습니다.")
    else:
        for i, news in enumerate(news_list, 1):
            content.append(f"[{i}] {news['title']}\n📝 요약: {news['summary']}\n🔗 링크: {news['link']}\n")
    
    msg = MIMEMultipart(); msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [완성판] {today} 뉴스 리포트"
    msg.attach(MIMEText("\n".join(content), 'plain'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
