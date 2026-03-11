import requests
import smtplib
import os
import feedparser
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 1. 환경 변수 설정
NAVER_ID = os.environ.get("NAVER_ID")
NAVER_SECRET = os.environ.get("NAVER_SECRET")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PW = os.environ.get("GMAIL_PW")
GH_TOKEN = os.environ.get("GH_TOKEN")
REPO = "girllangjak/ai-news-scraper" # 사용자님의 레포지토리 경로

def get_topic_from_issue():
    """GitHub 이슈 탭에서 'Open' 상태인 최신 글의 제목을 검색어로 가져옴"""
    url = f"https://api.github.com/repos/{REPO}/issues?state=open"
    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        res = requests.get(url, headers=headers)
        issues = res.json()
        if issues and isinstance(issues, list):
            # 가장 최근에 올라온 이슈 제목 반환
            return issues[0]['title']
    except Exception as e:
        print(f"이슈 읽기 실패: {e}")
    return "국내 주요 뉴스 TOP 5" # 이슈가 없거나 에러 날 때 기본값

def get_naver_news(query):
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(query)}&display=5&sort=sim"
    headers = {"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}
    try:
        res = requests.get(url, headers=headers).json()
        items = res.get('items', [])
        content = f"🔹 네이버 뉴스: '{query}'\n"
        for i, item in enumerate(items, 1):
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
            content += f"{i}. {title}\n   🔗 {item['link']}\n"
        return content
    except: return "네이버 수집 중 오류\n"

def get_google_news(query):
    rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        content = f"\n🔹 구글 뉴스: '{query}'\n"
        for i, entry in enumerate(feed.entries[:5], 1):
            content += f"{i}. {entry.title}\n   🔗 {entry.link}\n"
        return content
    except: return "구글 수집 중 오류\n"

if __name__ == "__main__":
    # 1. 이슈 제목에서 검색어 결정
    search_topic = get_topic_from_issue()
    print(f"현재 검색어: {search_topic}")

    # 2. 뉴스 수집
    naver_res = get_naver_news(search_topic)
    google_res = get_google_news(search_topic)

    # 3. 메일 구성
    today = datetime.now().strftime('%m월 %d일')
    body = f"🚀 {today} '{search_topic}' 리포트입니다.\n\n"
    body += "="*50 + "\n" + naver_res + "="*50 + "\n" + google_res
    
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg['Subject'] = f"📅 [뉴스] {today} {search_topic}"
    msg.attach(MIMEText(body, 'plain'))

    # 4. 발송
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PW)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        print("✅ 발송 성공!")
    except Exception as e:
        print(f"❌ 발송 실패: {e}")
