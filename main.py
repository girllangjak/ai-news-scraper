import requests
import smtplib
import os
import feedparser # 구글 뉴스 RSS를 읽기 위한 라이브러리
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# GitHub Secrets 설정
NAVER_CLIENT_ID = os.environ.get("NAVER_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_SECRET")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PW = os.environ.get("GMAIL_PW")

# 1. 네이버 뉴스 수집 함수
def get_naver_news(query):
    url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=5&sort=sim"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    
    try:
        res = requests.get(url, headers=headers)
        items = res.json().get('items', [])
        content = f"🔹 네이버 선정 '{query}' 주요 뉴스\n"
        for i, item in enumerate(items, 1):
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"')
            content += f"{i}. {title}\n   🔗 {item['link']}\n"
        return content
    except:
        return "네이버 뉴스 수집 중 오류 발생\n"

# 2. 구글 뉴스(RSS) 수집 함수
def get_google_news(query):
    # 구글 뉴스 RSS URL (한국어 설정)
    encoded_query = quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
    
    try:
        feed = feedparser.parse(rss_url)
        content = f"\n🔹 구글 뉴스 선정 '{query}' 관련 이슈\n"
        # 상위 5개만 추출
        for i, entry in enumerate(feed.entries[:5], 1):
            content += f"{i}. {entry.title}\n   🔗 {entry.link}\n"
        return content
    except:
        return "구글 뉴스 수집 중 오류 발생\n"

def send_gmail(content):
    today = datetime.now().strftime('%Y-%m-%d')
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER 
    msg['Subject'] = f"📅 [국내 이슈 TOP 5] {today} 뉴스 리포트"
    msg.attach(MIMEText(content, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PW)
        server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())

if __name__ == "__main__":
    # 검색어 설정
    search_query = "대한민국 주요 뉴스" 
    
    # 데이터 통합
    naver_part = get_naver_news(search_query)
    google_part = get_google_news(search_query)
    
    total_content = "🚀 오늘 아침 국내 주요 이슈 요약입니다.\n\n"
    total_content += "="*50 + "\n"
    total_content += naver_part
    total_content += "="*50 + "\n"
    total_content += google_part
    total_content += "\n" + "="*50
    
    send_gmail(total_content)
