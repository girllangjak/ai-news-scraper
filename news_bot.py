import requests
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 1. 설정 관리
CONFIG = {
    "NAVER_ID": os.environ.get("NAVER_ID"),
    "NAVER_SECRET": os.environ.get("NAVER_SECRET"),
    "GMAIL_USER": os.environ.get("GMAIL_USER"),
    "GMAIL_PW": os.environ.get("GMAIL_PW"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"),
    "REPO": "girllangjak/ai-news-scraper",
    "SEARCH_LIMIT": 15,
    "FINAL_COUNT": 5, # 요약 품질을 위해 개수를 5개로 정예화
}

def get_target_topic():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        return res[0]['title'] if res and isinstance(res, list) else "오늘의 주요 뉴스"
    except: return "오늘의 주요 뉴스"

def get_ai_summary(title):
    """Gemini API를 사용하여 기사 제목 기반 핵심 요약 생성"""
    if not CONFIG["GEMINI_API_KEY"]: return "요약 기능을 사용할 수 없습니다. (API 키 미설정)"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"다음 뉴스 제목을 바탕으로 이 기사가 담고 있을 핵심 내용을 전문가의 시각에서 딱 2줄로 요약해줘. \n뉴스 제목: {title}"
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        res = response.json()
        if 'candidates' in res:
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        return "내용 요약 중 오류가 발생했습니다."
    except:
        return "요약을 불러올 수 없습니다."

def fetch_news(query):
    refined_query = f"{query} -광고 -홍보 -이벤트"
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(refined_query)}&display={CONFIG['SEARCH_LIMIT']}&sort=sim"
    headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
    
    try:
        items = requests.get(url, headers=headers, timeout=10).json().get('items', [])
        results = []
        seen = set()

        for item in items:
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
            fingerprint = title.replace(" ", "")[:10]
            
            if fingerprint not in seen:
                # 요약 추가
                summary = get_ai_summary(title)
                results.append({"title": title, "link": item['link'], "summary": summary})
                seen.add(fingerprint)
            
            if len(results) >= CONFIG['FINAL_COUNT']: break
        return results
    except: return []

if __name__ == "__main__":
    topic = get_target_topic()
    news_list = fetch_news(topic)
    
    today = datetime.now().strftime('%Y-%m-%d')
    content = [f"🤖 AI 분석관이 선별한 오늘의 뉴스: {topic}\n", "="*50]
    
    for i, news in enumerate(news_list, 1):
        content.append(f"[{i}] {news['title']}")
        content.append(f"📝 AI 요약: {news['summary']}")
        content.append(f"🔗 링크: {news['link']}\n")
    
    content.append("="*50)
    content.append(f"발송 일시: {datetime.now().strftime('%H:%M:%S')}")

    msg = MIMEMultipart()
    msg['From'], msg['To'] = CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [AI 요약 리포트] {today} - {topic}"
    msg.attach(MIMEText("\n".join(content), 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
    print("✅ 요약 포함 리포트 발송 완료!")
