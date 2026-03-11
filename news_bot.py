import requests
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 환경 변수 불러오기
NAVER_ID = os.environ.get("NAVER_ID")
NAVER_SECRET = os.environ.get("NAVER_SECRET")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PW = os.environ.get("GMAIL_PW")
GH_TOKEN = os.environ.get("GH_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") # 여기서 키를 읽습니다.
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
    res = requests.get(url, headers=headers).json()
    items = res.get('items', [])
    titles = [item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"') for item in items]
    links = [item['link'] for item in items]
    return titles, links

def get_ai_analysis(topic, news_titles):
    """Gemini API를 직접 호출하여 분석 결과를 가져옵니다."""
    if not GEMINI_API_KEY:
        return "⚠️ Gemini API 키가 설정되지 않았습니다."
    
    # Gemini 1.5 Flash 모델 사용
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"주제: {topic}\n뉴스제목들: {news_titles}\n\n이 뉴스들을 읽고 1.현재 상황 요약(3줄), 2.향후 미래 전망 예측(3줄)을 한국어로 작성해줘."
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        res = requests.post(url, headers=headers, json=data).json()
        return res['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"⚠️ AI 분석 실패: {str(e)}"

if __name__ == "__main__":
    search_topic = get_topic_from_issue()
    titles, links = get_naver_news(search_topic)
    
    # AI 전망 분석 실행
    ai_report = get_ai_analysis(search_topic, titles)

    today = datetime.now().strftime('%Y-%m-%d')
    body = f"🚀 {today} AI 뉴스 분석 리포트\n\n"
    body += f"📌 주제: {search_topic}\n"
    body += "="*50 + "\n"
    body += f"🤖 [AI의 미래 전망 예측]\n\n{ai_report}\n"
    body += "="*50 + "\n\n"
    body += "📑 관련 뉴스 링크:\n"
    for i, (t, l) in enumerate(zip(titles, links), 1):
        body += f"{i}. {t}\n   🔗 {l}\n"
    
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg['Subject'] = f"📅 [AI 전망] {today} - {search_topic}"
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_PW)
        server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
    print("✅ 발송 완료!")
