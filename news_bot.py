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
    """HTML 태그 및 특수문자 제거로 AI 오류 방지"""
    if not text: return ""
    clean = re.compile('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});')
    return re.sub(clean, '', text).strip()

def call_gemini(prompt):
    """안정적인 API 호출을 위한 예외 처리 강화"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=20)
        res = response.json()
        if 'candidates' in res:
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        return "요약 불가 (AI 응답 구조 이상)"
    except Exception as e:
        return f"요약 실패 (통신 장애)"

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
            title = clean_text(item['title'])
            desc = clean_text(item['description'])
            prompt = f"다음 뉴스 제목과 본문을 한국어 한 문장으로 요약해줘.\n제목: {title}\n내용: {desc}"
            summary = call_gemini(prompt)
            results.append({"title": title, "summary": summary})
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
            summary = call_gemini(f"영문 뉴스 '{title}'을 한국어로 번역 및 요약해줘.")
            results.append({"title": title, "summary": summary})
        return results
    except: return []

if __name__ == "__main__":
    topic = get_target_topic()
    
    # 데이터 수집
    naver_res = fetch_naver_news(topic)
    target_gl, eng_query = analyze_context(topic)
    google_res = fetch_google_news(target_gl, eng_query)
    
    # [신규] 국내 vs 국외 시각 차이 비교 분석
    all_naver = " ".join([n['summary'] for n in naver_res])
    all_google = " ".join([g['summary'] for g in google_res])
    insight_prompt = f"국내 뉴스 요약: {all_naver}\n\n해외 뉴스 요약: {all_google}\n\n위 내용을 바탕으로 국내외 시각 차이를 한국어 한 문장으로 통찰력 있게 분석해줘."
    comparison = call_gemini(insight_prompt)

    # 메일 작성
    today = datetime.now().strftime('%Y-%m-%d')
    content = [f"📊 AI 입체 분석 리포트: {topic}", "="*50]
    
    content.append(f"\n💡 [AI 통찰: 국내외 시각 차이]\n{comparison}")
    
    content.append(f"\n\n[🇰🇷 국내 주요 보도 요약]")
    for n in naver_res:
        content.append(f"- {n['title']}\n  📌 {n['summary']}")
        
    content.append(f"\n\n[🌏 현지({target_gl}) 및 외신 요약]")
    for g in google_res:
        content.append(f"- {g['title']}\n  📌 {g['summary']}")
    
    content.append("\n" + "="*50)
    
    msg = MIMEMultipart(); msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [심층 분석] {today} - {topic}"
    msg.attach(MIMEText("\n".join(content), 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
    print(f"✅ 리포트 발송 성공")
