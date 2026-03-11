import requests, smtplib, os, feedparser
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 1. 환경 변수 가져오기
NAVER_ID = os.environ.get("NAVER_ID")
NAVER_SECRET = os.environ.get("NAVER_SECRET")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PW = os.environ.get("GMAIL_PW")

def get_news_report(query):
    # 네이버
    n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(query)}&display=5&sort=sim"
    n_res = requests.get(n_url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}).json()
    # 구글
    g_feed = feedparser.parse(f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko")
    
    report = f"📢 오늘의 '{query}' 주요 소식\n" + "="*50 + "\n\n"
    for item in n_res.get('items', []):
        t = item['title'].replace('<b>','').replace('</b>','')
        report += f"● {t}\n   🔗 {item['link']}\n"
    report += "\n" + "="*50 + "\n[구글 RSS 추가 이슈]\n"
    for entry in g_feed.entries[:5]:
        report += f"● {entry.title}\n   🔗 {entry.link}\n"
    return report

if __name__ == "__main__":
    content = get_news_report("국내 주요 뉴스 TOP 5")
    msg = MIMEMultipart()
    msg['Subject'] = f"📬 [최신 업데이트] {datetime.now().strftime('%m/%d')} 국내 이슈 리포트"
    msg['From'] = msg['To'] = GMAIL_USER
    msg.attach(MIMEText(content, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_PW)
        server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
    print("✅ 새로운 버전 발송 완료!")
