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
REPO = "girllangjak/ai-news-scraper"

def get_topic_from_issue():
    """GitHub 이슈에서 주제 가져오기"""
    url = f"https://api.github.com/repos/{REPO}/issues?state=open"
    headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers).json()
        if res and isinstance(res, list): return res[0]['title']
    except: pass
    return "오늘의 주요 뉴스"

def get_naver_news(query):
    """네이버 뉴스 검색"""
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(query)}&display=10&sort=sim"
    headers = {"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}
    try:
        res = requests.get(url, headers=headers).json()
        items = res.get('items', [])
        titles = [item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&") for item in items]
        links = [item['link'] for item in items]
        return titles, links
    except: return [], []

if __name__ == "__main__":
    # 1. 데이터 수집
    search_topic = get_topic_from_issue()
    titles, links = get_naver_news(search_topic)

    # 2. 메일 본문 구성 (분석 기능 제거, 뉴스 리스트만 강조)
    today = datetime.now().strftime('%Y-%m-%d')
    body = f"🗞️ {today} 실시간 뉴스 리포트\n\n"
    body += f"📌 검색 주제: {search_topic}\n"
    body += "="*50 + "\n"
    
    if titles:
        for i, (t, l) in enumerate(zip(titles, links), 1):
            body += f"{i}. {t}\n   🔗 {l}\n\n"
    else:
        body += "검색된 뉴스 결과가 없습니다. 주제를 확인해 주세요."
    
    body += "="*50 + "\n"
    body += "※ AI 분석 기능은 현재 서버 점검으로 인해 제외되었습니다."

    # 3. 이메일 발송
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg['Subject'] = f"📅 [뉴스 리포트] {today} - {search_topic}"
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PW)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        print("✅ 뉴스 리포트 발송 완료!")
    except Exception as e:
        print(f"❌ 발송 실패: {e}")
