import requests
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# GitHub Secrets에서 보안 정보를 가져옵니다.
NAVER_CLIENT_ID = os.environ.get("NAVER_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_SECRET")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PW = os.environ.get("GMAIL_PW")

def get_news(query):
    url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=5&sort=date"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    res = requests.get(url, headers=headers)
    items = res.json().get('items', [])
    
    content = f"📢 오늘의 '{query}' 뉴스 스크랩\n" + "="*40 + "\n\n"
    for i, item in enumerate(items, 1):
        title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
        content += f"{i}. {title}\n🔗 바로가기: {item['link']}\n\n"
    return content

def send_gmail(content):
    today = datetime.now().strftime('%Y-%m-%d')
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER 
    msg['Subject'] = f"📬 [AI 뉴스 레터] {today} 스크랩 결과"
    msg.attach(MIMEText(content, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PW)
        server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())

if __name__ == "__main__":
    news_data = get_news("AI 스크립트")
    send_gmail(news_data)
