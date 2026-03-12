import requests
import smtplib
import os
import xml.etree.ElementTree as ET
import json
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
}

def call_gemini(prompt):
    """Gemini 3 Flash Preview를 호출하는 공통 함수"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, timeout=15).json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return ""

def get_target_topic():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        return res[0]['title'] if isinstance(res, list) and len(res) > 0 else "오늘의 주요 뉴스"
    except: return "오늘의 주요 뉴스"

def analyze_context(topic):
    """주제를 보고 관련 국가 코드(gl)와 영어 검색어를 추출"""
    prompt = f"주제 '{topic}'과 가장 관련 깊은 국가의 2자리 코드(ISO)와 영어 검색어를 JSON 형식으로 알려줘. 예: {{'gl': 'US', 'query': 'Search Term'}}"
    result = call_gemini(prompt)
    try:
        # JSON 부분만 추출하여 파싱
        data = json.loads(result[result.find('{'):result.rfind('}')+1])
        return data.get('gl', 'US'), data.get('query', topic)
    except:
        return "US", topic

def fetch_google_news(gl, query):
    """설정된 국가의 구글 뉴스 RSS 검색 (현지 설정 적용)"""
    rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-{gl}&gl={gl}&ceid={gl}:en"
    try:
        res = requests.get(rss_url, timeout=10)
        root = ET.fromstring(res.text)
        results = []
        for item in root.findall('.//item')[:4]:
            title = item.find('title').text
            link = item.find('link').text
            # 영문 기사를 한글로 요약 요청
            summary = call_gemini(f"영문 뉴스 '{title}'을 한국어로 핵심 요약해줘.")
            results.append({"title": title, "link": link, "summary": summary})
        return results
    except: return []

def fetch_naver_news(topic):
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=5&sort=sim"
    headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
    try:
        items = requests.get(url, headers=headers, timeout=10).json().get('items', [])
        results = []
        for item in items:
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"')
            summary = call_gemini(f"뉴스 '{title}'을 한국어 한 문장으로 요약해줘.")
            results.append({"title": title, "link": item['link'], "summary": summary})
        return results
    except: return []

if __name__ == "__main__":
    topic = get_target_topic()
    
    # 1. 네이버 스크랩
    naver_res = fetch_naver_news(topic)
    
    # 2. 주제 분석 (국가 및 검색어 선정)
    target_gl, eng_query = analyze_context(topic)
    
    # 3. 해당 국가 구글 뉴스 스크랩 (한글화 포함)
    google_res = fetch_google_news(target_gl, eng_query)
    
    # 메일 구성
    today = datetime.now().strftime('%Y-%m-%d')
    content = [f"🌐 글로벌 입체 분석 보고서: {topic}", "="*50]
    content.append(f"\n[🇰🇷 국내 보도 현황]\n" + "\n".join([f"- {n['title']}\n  📝 {n['summary']}" for n in naver_res]))
    content.append(f"\n\n[🌏 현지({target_gl}) 보도 및 외신 분석]\n" + "\n".join([f"- {g['title']}\n  📝 {g['summary']}" for g in google_res]))
    
    msg = MIMEMultipart(); msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [글로벌 분석] {today} - {topic}"
    msg.attach(MIMEText("\n".join(content), 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
    print(f"✅ {target_gl} 지역 기반 리포트 발송 완료")
