import requests
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 환경 변수 (GitHub Secrets)
NAVER_ID = os.environ.get("NAVER_ID")
NAVER_SECRET = os.environ.get("NAVER_SECRET")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PW = os.environ.get("GMAIL_PW")
GH_TOKEN = os.environ.get("GH_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
REPO = "girllangjak/ai-news-scraper"

def get_topic_from_issue():
    url = f"https://api.github.com/repos/{REPO}/issues?state=open"
    headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers).json()
        if res and isinstance(res, list): return res[0]['title']
    except: pass
    return "국내 주요 뉴스"

def get_naver_news(query):
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(query)}&display=7&sort=sim"
    headers = {"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}
    try:
        res = requests.get(url, headers=headers).json()
        items = res.get('items', [])
        titles = [item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&") for item in items]
        links = [item['link'] for item in items]
        return titles, links
    except: return [], []

def get_ai_analysis(topic, news_titles):
    if not GEMINI_API_KEY: return "⚠️ API 키 설정 필요"
    
    # ⭐ [최후의 수단] 모델명을 gemini-1.0-pro로 강제 변경했습니다. 
    # 거의 모든 키에서 이 모델은 'NOT_FOUND' 에러 없이 작동합니다.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.0-pro:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    news_str = "\n".join(news_titles)
    prompt = f"주제: {topic}\n뉴스제목: {news_str}\n\n1.현상황 요약, 2.미래 전망을 각각 3줄씩 한국어로 작성해."
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        res = response.json()
        
        # 답변 추출
        if 'candidates' in res and len(res['candidates']) > 0:
            return res['candidates'][0]['content']['parts'][0]['text']
        
        return f"⚠️ 분석 실패. 응답 로그: {res}"
    except Exception as e:
        return f"⚠️ 에러: {str(e)}"

if __name__ == "__main__":
    search_topic = get_topic_from_issue()
    titles, links = get_naver_news(search_topic)
    ai_report = get_ai_analysis(search_topic, titles) if titles else "뉴스가 없습니다."

    today = datetime.now().strftime('%Y-%m-%d')
    body = f"🚀 {today} AI 뉴스 분석 리포트\n\n📌 주제: {search_topic}\n"
    body += "="*50 + "\n🤖 [AI의 미래 전망 예측]\n\n" + ai_report + "\n"
    body += "="*50 + "\n\n📑 관련 뉴스 링크:\n"
    for i, (t, l) in enumerate(zip(titles, links), 1):
        body += f"{i}. {t}\n   🔗 {l}\n"
    
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg['Subject'] = f"📅 [AI 뉴스 리포트] {today} - {search_topic}"
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_PW)
        server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
    print("✅ 발송 완료!")
