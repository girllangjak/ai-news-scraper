import requests
import smtplib
import os
import xml.etree.ElementTree as ET
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

CONFIG = {
    "NAVER_ID": os.environ.get("NAVER_ID"),
    "NAVER_SECRET": os.environ.get("NAVER_SECRET"),
    "GMAIL_USER": os.environ.get("GMAIL_USER"),
    "GMAIL_PW": os.environ.get("GMAIL_PW"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"),
    "REPO": "girllangjak/ai-news-scraper",
}

def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, timeout=15).json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return "요약 생성 중 오류"

def get_target_topic():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        return res[0]['title'] if isinstance(res, list) and len(res) > 0 else "오늘의 뉴스"
    except: return "오늘의 뉴스"

def analyze_context(topic):
    prompt = f"주제 '{topic}'과 가장 관련 깊은 국가의 2자리 코드(ISO)와 영어 검색어를 JSON 형식으로 알려줘. 예: {{'gl': 'US', 'query': 'Search Term'}}"
    result = call_gemini(prompt)
    try:
        data = json.loads(result[result.find('{'):result.rfind('}')+1])
        return data.get('gl', 'US'), data.get('query', topic)
    except: return "US", topic

def fetch_naver_news(topic):
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=5&sort=sim"
    headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
    try:
        items = requests.get(url, headers=headers, timeout=10).json().get('items', [])
        results = []
        for item in items:
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"')
            description = item['description'].replace("<b>", "").replace("</b>", "") # 네이버에서 제공하는 짧은 본문 활용
            # [수정] 제목과 요약 정보를 합쳐서 더 정밀하게 요약 요청
            prompt = f"다음 뉴스 제목과 요약문을 읽고, 한국어로 핵심 내용을 한 줄로 깊이 있게 요약해줘.\n제목: {title}\n요약문: {description}"
            summary = call_gemini(prompt)
            results.append({"title": title, "link": item['link'], "summary": summary})
        return results
    except: return []

def fetch_google_news(gl, query):
    rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-{gl}&gl={gl}&ceid={gl}:en"
    try:
        res = requests.get(rss_url, timeout=10)
        root = ET.fromstring(res.text)
        results = []
        for item in root.findall('.//item')[:4]:
            title = item.find('title').text
            link = item.find('link').text
            summary = call_gemini(f"영문 뉴스 '{title}'을 한국어로 번역하고 핵심을 한 줄로 요약해줘.")
            results.append({"title": title, "link": link, "summary": summary})
        return results
    except: return []

if __name__ == "__main__":
    topic = get_target_topic()
    naver_res = fetch_naver_news(topic)
    target_gl, eng_query = analyze_context(topic)
    google_res = fetch_google_news(target_gl, eng_query)
    
    today = datetime.now().strftime('%Y-%m-%d')
    content = [f"📊 AI 입체 분석 리포트: {topic}", "="*50]
    
    content.append(f"\n[🇰🇷 국내 언론 핵심 요약]")
    for n in naver_res:
        content.append(f"- {n['title']}\n  📌 분석 요약: {n['summary']}")
        
    content.append(f"\n\n[🌏 현지({target_gl}) 및 외신 요약]")
    for g in google_res:
        content.append(f"- {g['title']}\n  📌 번역 요약: {g['summary']}")
    
    content.append("\n" + "="*50)
    
    msg = MIMEMultipart(); msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [심층 분석] {today} - {topic}"
    msg.attach(MIMEText("\n".join(content), 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
    print(f"✅ 리포트 발송 완료")
