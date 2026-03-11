import requests
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 환경 변수
NAVER_ID = os.environ.get("NAVER_ID")
NAVER_SECRET = os.environ.get("NAVER_SECRET")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PW = os.environ.get("GMAIL_PW")
GH_TOKEN = os.environ.get("GH_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
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
    try:
        res = requests.get(url, headers=headers).json()
        items = res.get('items', [])
        titles = [item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"') for item in items]
        links = [item['link'] for item in items]
        return titles, links
    except: return [], []

def get_ai_analysis(topic, news_titles):
    if not GEMINI_API_KEY: return "⚠️ API 키 설정 필요"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    news_str = "\n".join(news_titles)
    # 프롬프트 수정: 객관적인 분석가 역할을 부여하여 안전 필터 회피 유도
    prompt = (
        f"당신은 전문 뉴스 분석가입니다. 다음 뉴스들을 바탕으로 '객관적인 경제 및 사회 트렌드'를 분석하세요.\n"
        f"주제: {topic}\n뉴스들: {news_str}\n\n"
        f"위 내용을 토대로 1.현재 상황 요약(3줄), 2.향후 미래 전망 및 사회적 영향(3줄)을 한국어로 작성하세요."
    )

    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        # 안전 설정을 낮추어 분석이 중단되지 않게 함
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }
    
    try:
        res = requests.post(url, headers=headers, json=data).json()
        # 데이터가 비어있는지 꼼꼼하게 체크
        if 'candidates' in res and res['candidates'][0].get('content'):
            return res['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"⚠️ AI가 내용을 생성하지 못했습니다. (사유: {res.get('promptFeedback', '알 수 없음')})"
    except Exception as e:
        return f"⚠️ 분석 에러 발생: {str(e)}"

if __name__ == "__main__":
    search_topic = get_topic_from_issue()
    titles, links = get_naver_news(search_topic)
    
    ai_report = get_ai_analysis(search_topic, titles)

    today = datetime.now().strftime('%Y-%m-%d')
    body = f"🚀 {today} AI 뉴스 분석 리포트\n\n📌 주제: {search_topic}\n"
    body += "="*50 + "\n🤖 [AI의 미래 전망 예측]\n\n" + ai_report + "\n"
    body += "="*50 + "\n\n📑 관련 뉴스 링크:\n"
    for i, (t, l) in enumerate(zip(titles, links), 1):
        body += f"{i}. {t}\n   🔗 {l}\n"
    
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg['Subject'] = f"📅 [AI 뉴스 리포트] {today} - {search_topic}"
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_PW)
        server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
    print("✅ 발송 완료!")
