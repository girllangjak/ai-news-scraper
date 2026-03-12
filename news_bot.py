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
        res = requests.post(url, json=payload, timeout=20).json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "핵심 내용을 요약 중입니다... (분석 지연)"

def get_target_topic():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers).json()
        return res[0]['title'] if isinstance(res, list) and len(res) > 0 else "오늘의 뉴스"
    except: return "오늘의 뉴스"

def analyze_context(topic):
    prompt = f"주제 '{topic}'과 가장 관련 깊은 국가 코드(ISO)와 영어 검색어를 JSON으로 알려줘. {{'gl': 'US', 'q': 'term'}}"
    try:
        result = call_gemini(prompt)
        data = json.loads(result[result.find('{'):result.rfind('}')+1])
        return data.get('gl', 'US'), data.get('q', topic)
    except: return "US", topic

def fetch_naver_news(topic):
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=5&sort=sim"
    headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
    results = []
    try:
        items = requests.get(url, headers=headers).json().get('items', [])
        for item in items:
            title = clean_text(item['title'])
            desc = clean_text(item['description'])
            # 제목과 설명을 모두 주어 요약 품질을 높임
            summary = call_gemini(f"이 기사를 한국어 한 문장으로 요약해줘: {title}. 내용: {desc}")
            results.append({"title": title, "summary": summary, "link": item['link']})
    except: pass
    return results

def fetch_google_news(gl, query):
    rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-{gl}&gl={gl}&ceid={gl}:en"
    results = []
    try:
        res = requests.get(rss_url, timeout=10)
        root = ET.fromstring(res.text)
        for item in root.findall('.//item')[:4]:
            title = item.find('title').text
            # 영문 제목을 한글로 요약/번역
            summary = call_gemini(f"영문 기사 제목 '{title}'을 한국어로 번역하고 핵심 내용을 분석해줘.")
            results.append({"title": title, "summary": summary, "link": item.find('link').text})
    except: pass
    return results

if __name__ == "__main__":
    topic = get_target_topic()
    naver_res = fetch_naver_news(topic)
    target_gl, eng_query = analyze_context(topic)
    google_res = fetch_google_news(target_gl, eng_query)
    
    today = datetime.now().strftime('%Y-%m-%d')
    content = [f"📊 AI 입체 분석 리포트: {topic}", "="*50]
    
    content.append(f"\n[🇰🇷 국내 주요 보도 요약]")
    for n in naver_res:
        content.append(f"- {n['title']}\n  📌 {n['summary']}\n  🔗 {n['link']}")
        
    content.append(f"\n\n[🌏 현지({target_gl}) 및 외신 요약 (한글화)]")
    for g in google_res:
        content.append(f"- {g['title']}\n  📌 {g['summary']}\n  🔗 {g['link']}")
    
    msg = MIMEMultipart(); msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [분석완료] {today} - {topic}"
    msg.attach(MIMEText("\n".join(content), 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
