import requests, smtplib, os, feedparser
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 1. 환경 변수
NAVER_ID = os.environ.get("NAVER_ID")
NAVER_SECRET = os.environ.get("NAVER_SECRET")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PW = os.environ.get("GMAIL_PW")

def get_news_content(query):
    # 네이버 수집
    n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(query)}&display=5&sort=sim"
    n_res = requests.get(n_url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}).json()
    
    # 구글 수집
    g_feed = feedparser.parse(f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko")
    
    res = f"📢 '{query}' 뉴스 리포트 ({datetime.now().strftime('%Y-%m-%d')})\n" + "="*50 + "\n\n"
    res += "[네이버 뉴스 주요 소식]\n"
    for item in n_res.get('items', []):
        res += f"- {item['title'].replace('<b>','').replace('</b>','')} \n  Link: {item['link']}\n"
    
    res += "\n" + "="*50 + "\n[구글 RSS 주요 이슈]\n"
    for entry in g_feed.entries[:5]:
        res += f"- {entry.title} \n  Link: {entry.link}\n"
    return res

if __name__ == "__main__":
    content = get_news_content("국내 주요 뉴스 TOP 5") # 주제 변경 확인!
    
    msg = MIMEMultipart()
    msg['Subject'] = f"📅 [새로운 리포트] {datetime.now().strftime('%m월 %d일')} 뉴스"
    msg['From'] = msg['To'] = GMAIL_USER
    msg.attach(MIMEText(content, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_PW)
        server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
    print("✅ 발송 완료!")
