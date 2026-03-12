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

# [설정] GitHub Secrets 및 환경 변수 연동
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
    """HTML 태그 및 특수문자 제거로 요약 오류 방지"""
    if not text: return ""
    clean = re.compile('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});')
    return re.sub(clean, '', text).strip()

def call_gemini(prompt):
    """Gemini 3 Flash Preview 호출"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=25)
        res = response.json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return "요약 생성 중 오류 (AI 응답 지연)"

def get_target_topics():
    """GitHub Issue 제목을 콤마(,) 기준으로 분리하여 리스트화"""
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        if isinstance(res, list) and len(res) > 0:
            return [t.strip() for t in res[0]['title'].split(',') if t.strip()]
        return ["오늘의 경제 뉴스"]
    except: return ["오늘의 경제 뉴스"]

def fetch_naver_news(topic):
    """네이버 뉴스 수집 및 요약"""
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=3&sort=sim"
    headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
    results = []
    try:
        items = requests.get(url, headers=headers, timeout=10).json().get('items', [])
        for item in items:
            title, desc = clean_text(item['title']), clean_text(item['description'])
            summary = call_gemini(f"뉴스 내용을 한국어 한 문장으로 요약해줘.\n제목: {title}\n내용: {desc}")
            results.append({"title": title, "summary": summary, "link": item['link']})
    except: pass
    return results

def fetch_google_news(topic):
    """AI가 국가를 판단하여 글로벌 현지 뉴스 수집"""
    # 1. 관련 국가와 검색어 분석
    analysis = call_gemini(f"주제 '{topic}'과 가장 관련 깊은 국가 코드(ISO 2자리)와 영어 검색어를 JSON으로 알려줘. {{'gl': 'US', 'q': 'term'}}")
    try:
        data = json.loads(analysis[analysis.find('{'):analysis.rfind('}')+1])
        gl, query = data.get('gl', 'US'), data.get('q', topic)
    except: gl, query = "US", topic

    # 2. 구글 RSS 검색
    rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-{gl}&gl={gl}&ceid={gl}:en"
    results = []
    try:
        res = requests.get(rss_url, timeout=10)
        root = ET.fromstring(res.text)
        for item in root.findall('.//item')[:2]:
            title = item.find('title').text
            summary = call_gemini(f"영문 뉴스 '{title}'을 한국어로 핵심 요약해줘.")
            results.append({"title": title, "summary": summary, "link": item.find('link').text, "country": gl})
    except: pass
    return results

if __name__ == "__main__":
    topics = get_target_topics()
    naver_all, google_all = [], []
    
    for t in topics:
        naver_all.extend(fetch_naver_news(t))
        google_all.extend(fetch_google_news(t))
    
    # 💡 국내외 시각 차이 비교 분석 (통찰 섹션)
    summary_text = "국내 뉴스: " + " ".join([n['summary'] for n in naver_all[:3]]) + \
                   "\n해외 뉴스: " + " ".join([g['summary'] for g in google_all[:3]])
    insight = call_gemini(f"다음 뉴스 요약본을 보고 국내외 시각 차이를 통찰력 있게 한 문장으로 분석해줘.\n{summary_text}")

    # ✉️ 메일 본문 구성
    today = datetime.now().strftime('%Y-%m-%d')
    content = [f"📊 AI 입체 분석 리포트: {', '.join(topics)}", "="*50]
    content.append(f"\n💡 [AI 인사이트: 국내외 시각 차이]\n{insight}")
    
    content.append(f"\n[🇰🇷 국내 주요 보도 ({len(naver_all)}건)]")
    for n in naver_all:
        content.append(f"- {n['title']}\n  📌 {n['summary']}\n  🔗 {n['link']}")
        
    content.append(f"\n\n[🌏 글로벌 현지 보도 ({len(google_all)}건)]")
    for g in google_all:
        content.append(f"({g['country']}) - {g['title']}\n  📌 {g['summary']}\n  🔗 {g['link']}")
    
    content.append("\n" + "="*50)

    # 🚀 메일 발송
    msg = MIMEMultipart(); msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [멀티 분석] {today} - {topics[0]} 외 {len(topics)-1}건"
    msg.attach(MIMEText("\n".join(content), 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
    print("✅ 글로벌 멀티 분석 리포트 발송 성공")
