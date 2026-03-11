import requests
import smtplib
import os
import feedparser
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 1. GitHub Secrets에서 설정값 불러오기
NAVER_ID = os.environ.get("NAVER_ID")
NAVER_SECRET = os.environ.get("NAVER_SECRET")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PW = os.environ.get("GMAIL_PW")

def get_naver_news(query):
    """네이버 API를 이용한 뉴스 수집"""
    encoded_query = quote(query)
    url = f"https://openapi.naver.com/v1/search/news.json?query={encoded_query}&display=5&sort=sim"
    headers = {
        "X-Naver-Client-Id": NAVER_ID,
        "X-Naver-Client-Secret": NAVER_SECRET
    }
    try:
        res = requests.get(url, headers=headers)
        items = res.json().get('items', [])
        content = f"🔹 네이버 뉴스: '{query}' 검색 결과\n"
        for i, item in enumerate(items, 1):
            # HTML 태그 및 특수문자 제거
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
            content += f"{i}. {title}\n   🔗 {item['link']}\n"
        return content
    except Exception as e:
        return f"❌ 네이버 뉴스 수집 중 오류 발생: {e}\n"

def get_google_news(query):
    """구글 RSS를 이용한 뉴스 수집"""
    encoded_query = quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        content = f"\n🔹 구글 뉴스: '{query}' 관련 이슈\n"
        for i, entry in enumerate(feed.entries[:5], 1):
            content += f"{i}. {entry.title}\n   🔗 {entry.link}\n"
        return content
    except Exception as e:
        return f"❌ 구글 뉴스 수집 중 오류 발생: {e}\n"

if __name__ == "__main__":
    # ⭐ 주제 변경은 여기서 하세요!
    search_topic = "안경" 
    
    # 데이터 수집 실행
    naver_part = get_naver_news(search_topic)
    google_part = get_google_news(search_topic)
    
    # 메일 본문 구성
    today_date = datetime.now().strftime('%Y-%m-%d')
    total_body = f"🚀 {today_date} 뉴스 자동 리포트입니다.\n\n"
    total_body += "="*60 + "\n" + naver_part + "="*60 + "\n" + google_part + "="*60
    
    # 이메일 발송 설정
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg['Subject'] = f"📅 [뉴스 리포트] {datetime.now().strftime('%m월 %d일')} 업데이트"
    msg.attach(MIMEText(total_body, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PW)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        print("✅ 모든 과정이 성공적으로 완료되었습니다!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")
