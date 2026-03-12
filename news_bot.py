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

# [환경 설정]
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
    """HTML 태그 및 특수문자 제거"""
    if not text: return ""
    return re.sub('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});', '', text).strip()

def call_gemini(prompt):
    """Gemini API 호출 (통합 분석용)"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, timeout=40).json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "⚠️ 분석 엔진 응답 지연이 발생했습니다. 수동 확인이 필요합니다."

def get_target_topics():
    """GitHub 이슈에서 키워드 추출 (콤마 구분 대응)"""
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        if isinstance(res, list) and len(res) > 0:
            return [t.strip() for t in res[0]['title'].split(',') if t.strip()]
        return ["오늘의 뉴스"]
    except: return ["오늘의 뉴스"]

def fetch_data(topics):
    """네이버 및 구글 뉴스 원본 데이터 수집"""
    naver_raw, google_raw = [], []
    for topic in topics:
        # 네이버 뉴스
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=3&sort=sim"
        n_headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
        n_res = requests.get(n_url, headers=n_headers).json().get('items', [])
        for item in n_res:
            naver_raw.append({"title": clean_text(item['title']), "desc": clean_text(item['description']), "link": item['link']})
        
        # 구글 뉴스 (영문 검색)
        g_url = f"https://news.google.com/rss/search?q={quote(topic)}&hl=en-US&gl=US&ceid=US:en"
        g_res = requests.get(g_url, timeout=10)
        root = ET.fromstring(g_res.text)
        for item in root.findall('.//item')[:3]:
            google_raw.append({"title": item.find('title').text, "link": item.find('link').text})
    return naver_raw, google_raw

if __name__ == "__main__":
    # 1. 주제 로드
    topics = get_target_topics()
    
    # 2. 뉴스 원천 데이터 수집
    n_list, g_list = fetch_data(topics)
    
    # 3. 통합 분석 요청 (딱 한 번의 요청으로 모든 요약 완료)
    prompt = f"""
    당신은 전문 뉴스 분석가입니다. 아래 제공된 데이터를 기반으로 리포트를 작성하세요.
    
    [분석 주제]: {', '.join(topics)}
    [국내 데이터]: {json.dumps(n_list, ensure_ascii=False)}
    [해외 데이터]: {json.dumps(g_list, ensure_ascii=False)}
    
    [작성 양식]:
    1. 인사이트: 전체 뉴스를 종합하여 국내외 시각 차이를 한국어 한 문장으로 요약.
    2. 국내 주요 보도: 각 기사 제목 아래에 '📌 요약: [한국어 한 문장]' 작성.
    3. 글로벌 주요 보도: 영문 제목을 한국어로 번역하고 '📌 요약: [한국어 한 문장]' 작성.
    """
    
    final_report = call_gemini(prompt)

    # 4. 리포트 본문 구성 (링크 포함)
    today = datetime.now().strftime('%Y-%m-%d')
    footer = "\n\n🔗 [참조 링크 모음]\n"
    for item in n_list + g_list:
        footer += f"- {item['title'][:40]}... : {item['link']}\n"
        
    msg = MIMEMultipart(); msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [글로벌 인사이트] {today} - {topics[0]} 외"
    msg.attach(MIMEText(final_report + footer, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
    print("✅ 분석 리포트 발송 완료")
