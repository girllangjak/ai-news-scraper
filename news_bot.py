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
    return re.sub('<.*?>|&([a-z0-9]+|#[0-9]{1,6});', '', text).strip()

def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30).json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return "분석 불가"

# 1. 뉴스 데이터 수집 함수들
def get_news_data(topic):
    # 네이버 수집
    n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=5&sort=sim"
    n_headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
    naver_items = requests.get(n_url, headers=n_headers).json().get('items', [])
    
    # 구글 수집 (간소화)
    g_url = f"https://news.google.com/rss/search?q={quote(topic)}&hl=en-US&gl=US&ceid=US:en"
    g_res = requests.get(g_url)
    g_items = ET.fromstring(g_res.text).findall('.//item')[:4]
    
    return naver_items, g_items

if __name__ == "__main__":
    # 이슈 제목 가져오기
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}"}
    topic = requests.get(url, headers=headers).json()[0]['title']
    
    naver_raw, google_raw = get_news_data(topic)

    # [핵심] 모든 뉴스를 한꺼번에 보내서 딱 한 번만 요약 요청 (속도 향상 및 누락 방지)
    full_prompt = f"""
    주제: {topic}
    다음 뉴스 리스트를 분석해서 1)전체 요약 인사이트 2)개별 뉴스 요약(한국어 한 문장)을 작성해줘.
    
    [네이버 뉴스]
    {[(i['title'], i['description']) for i in naver_raw]}
    
    [구글 뉴스]
    {[i.find('title').text for i in google_raw]}
    
    형식:
    인사이트: (한 줄)
    - 기사제목: 요약내용
    """
    
    analysis_result = call_gemini(full_prompt)

    # 메일 발송
    today = datetime.now().strftime('%Y-%m-%d')
    msg = MIMEMultipart(); msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [심층분석] {today} - {topic}"
    msg.attach(MIMEText(f"📊 {topic} 분석 리포트\n\n{analysis_result}", 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
    print("✅ 발송 완료")
