import requests
import smtplib
import os
import xml.etree.ElementTree as ET
import json
import re
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

def clean_text(text):
    if not text: return ""
    clean = re.compile('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});')
    return re.sub(clean, '', text).strip()

def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=20)
        res = response.json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return "요약 생성 중 오류"

def get_target_topics():
    """콤마로 구분된 주제 리스트 반환"""
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        if isinstance(res, list) and len(res) > 0:
            full_title = res[0]['title']
            # 콤마로 분리하고 공백 제거
            return [t.strip() for t in full_title.split(',') if t.strip()]
        return ["오늘의 뉴스"]
    except: return ["오늘의 뉴스"]

def analyze_context(topic):
    prompt = f"주제 '{topic}'과 가장 관련 깊은 국가의 2자리 코드(ISO)와 영어 검색어를 JSON 형식으로 알려줘. 예: {{'gl': 'US', 'query': 'Search Term'}}"
    result = call_gemini(prompt)
    try:
        data = json.loads(result[result.find('{'):result.rfind('}')+1])
        return data.get('gl', 'US'), data.get('query', topic)
    except: return "US", topic

def fetch_naver_news(topic):
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=3&sort=sim"
    headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
    results = []
    try:
        items = requests.get(url, headers=headers, timeout=10).json().get('items', [])
        for item in items:
            title = clean_text(item['title'])
            desc = clean_text(item['description'])
            summary = call_gemini(f"뉴스 요약해줘.\n제목: {title}\n내용: {desc}")
            results.append({"title": title, "summary": summary})
    except: pass
    return results

def fetch_google_news(gl, query):
    rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-{gl}&gl={gl}&ceid={gl}:en"
    results = []
    try:
        res = requests.get(rss_url, timeout=10)
        root = ET.fromstring(res.text)
        for item in root.findall('.//item')[:2]:
            title = item.find('title').text
            summary = call_gemini(f"영문 뉴스 요약해줘: {title}")
            results.append({"title": title, "summary": summary})
    except: pass
    return results

if __name__ == "__main__":
    topics = get_target_topics()
    naver_total, google_total = [], []
    
    # 각 키워드별로 루프를 돌며 검색
    for topic in topics:
        naver_total.extend(fetch_naver_news(topic))
        target_gl, eng_query = analyze_context(topic)
        google_total.extend(fetch_google_news(target_gl, eng_query))
    
    # 시각 차 분석 (데이터가 너무 많으면 AI가 헷갈리므로 핵심만 전달)
    all_summary = " ".join([n['summary'] for n in naver_total[:5]])
    comparison = call_gemini(f"다음 뉴스들을 보고 국내외 시각 차이를 분석해줘: {all_summary}")

    # 메일 발송 로직 (중복 제거 및 구성)
    today = datetime.now().strftime('%Y-%m-%d')
    content = [f"📊 다각도 분석 리포트: {', '.join(topics)}", "="*50]
    content.append(f"\n💡 [AI 인사이트]\n{comparison}")
    
    content.append("\n[🇰🇷 국내 주요 뉴스]")
    for n in naver_total[:10]: # 최대 10개 출력
        content.append(f"- {n['title']}\n  📌 {n['summary']}")
        
    content.append("\n\n[🌏 글로벌 현지 뉴스]")
    for g in google_total[:6]:
        content.append(f"- {g['title']}\n  📌 {g['summary']}")
    
    msg = MIMEMultipart(); msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [멀티 분석] {today} - {topics[0]} 외"
    msg.attach(MIMEText("\n".join(content), 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
