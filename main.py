import requests
import smtplib
import os
import feedparser
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 1. 환경 변수 설정 (GitHub Secrets와 이름 일치 확인)
NAVER_CLIENT_ID = os.environ.get("NAVER_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_SECRET")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PW = os.environ.get("GMAIL_PW") # Secrets에 등록한 이름이 GMAIL_PW인지 확인하세요.

def get_naver_news(query):
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(query)}&display=5&sort=sim"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    try:
        res = requests.get(url, headers=headers)
        items = res.json().get('items', [])
        content = f"🔹 네이버 뉴스: '{query}' TOP 5\n"
        for i, item in enumerate(items, 1):
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
            content += f"{i}. {title}\n   🔗 {item['link']}\n"
        return content
    except Exception as e:
        return f"네이버 수집 오류: {e}\n"

def get_google_news(query):
    encoded_query = quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        content = f"\n🔹 구글 뉴스: '{query}' 관련 이슈\n"
        for i, entry in enumerate(feed.entries[:5], 1):
            content += f"{i}. {entry.title}\n   🔗 {entry.link}\n"
        return content
    except Exception as e:
        return f"구글 수집 오류: {e}\n"

if __name__ == "__main__":
    # 검색 주제 설정
    query = "국내 주요 뉴스"
    
    # 데이터 수집
    naver_res = get_naver_news(query)
    google_res = get_google_news(query)
    
    # 메일 본문 구성
    today_str = datetime.now().strftime('%Y-%m-%d')
    body = f"🚀 {today_str} 뉴스 리포트입니다.\n\n"
    body += "="*50 + "\n" + naver_res + "="*50 + "\n" + google_res + "="*50
    
    # 이메일 발송 설정
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg['Subject'] = f"📬 [뉴스 리포트] {datetime.now().strftime('%m월 %d일')} 국내 주요 이슈"
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PW)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        print("✅ 메일 발송 성공!")
    except Exception as e:
        print(f"❌ 발송 실패: {e}")
