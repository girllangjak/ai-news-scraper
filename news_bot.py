import requests
import smtplib
import os
import feedparser
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 1. 환경 변수 설정 (GitHub Secrets에서 가져옴)
NAVER_ID = os.environ.get("NAVER_ID")
NAVER_SECRET = os.environ.get("NAVER_SECRET")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PW = os.environ.get("GMAIL_PW")
GH_TOKEN = os.environ.get("GH_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
REPO = "girllangjak/ai-news-scraper"

def get_topic_from_issue():
    """GitHub 이슈 탭에서 'Open' 상태인 최신 글의 제목을 검색어로 가져옴"""
    url = f"https://api.github.com/repos/{REPO}/issues?state=open"
    headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers).json()
        if res and isinstance(res, list):
            return res[0]['title']
    except: pass
    return "국내 주요 뉴스"

def get_naver_news(query):
    """네이버 뉴스 수집"""
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(query)}&display=8&sort=sim"
    headers = {"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}
    try:
        res = requests.get(url, headers=headers).json()
        items = res.get('items', [])
        titles = [item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"') for item in items]
        links = [item['link'] for item in items]
        return titles, links
    except: return [], []

def get_ai_analysis(topic, news_titles):
    """Gemini AI를 이용한 뉴스 분석 및 미래 전망 예측"""
    if not GEMINI_API_KEY: return "⚠️ Gemini API 키가 설정되지 않았습니다."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # AI에게 줄 명령어(프롬프트)
    news_str = "\n".join(news_titles)
    prompt = f"주제: {topic}\n뉴스 제목들:\n{news_str}\n\n위 뉴스들을 분석해서 다음 양식으로 작성해줘:\n\n1. 📍 현재 상황 요약 (3줄 내외)\n2. 🔮 향후 1년 내 미래 전망 예측 (3줄 내외)\n3. 💡 우리가 주목해야 할 핵심 포인트 (2줄 내외)"
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        res = requests.post(url, headers=headers, json=data).json()
        return res['candidates'][0]['content']['parts'][0]['text']
    except:
        return "⚠️ AI 분석 중 오류가 발생했습니다. (API 키 혹은 할당량 확인 필요)"

if __name__ == "__main__":
    # 1. 이슈에서 주제 가져오기
    search_topic = get_topic_from_issue()
    print(f"🔍 현재 검색 주제: {search_topic}")

    # 2. 뉴스 데이터 수집
    titles, links = get_naver_news(search_topic)
    
    # 3. AI 분석 리포트 생성
    ai_report = get_ai_analysis(search_topic, titles)

    # 4. 메일 본문 구성
    today = datetime.now().strftime('%Y년 %m월 %d일')
    body = f"🤖 [AI 인텔리전스 리포트] {today}\n"
    body += f"주제: {search_topic}\n\n"
    body += "="*50 + "\n"
    body += f"📝 [AI 분석 결과 및 미래 전망]\n\n{ai_report}\n"
    body += "="*50 + "\n\n"
    body += "📑 [관련 주요 뉴스 기사]\n"
    for i, (t, l) in enumerate(zip(titles, links), 1):
        body += f"{i}. {t}\n   🔗 {l}\n"
    
    # 5. 이메일 발송
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg['Subject'] = f"📅 [AI 전망 리포트] {today} - {search_topic}"
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PW)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        print("✅ 리포트 발송 성공!")
    except Exception as e:
        print(f"❌ 발송 실패: {e}")
