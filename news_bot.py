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

def clean_text(text):
    if not text: return ""
    return re.sub('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});', '', text).strip()

def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, timeout=40).json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "⚠️ 분석 엔진 응답 지연으로 요약을 생성하지 못했습니다."

def get_target_topics():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            return [t.strip() for t in res[0]['title'].split(',') if t.strip()]
        return ["오늘의 주요 뉴스"]
    except: return ["오늘의 주요 뉴스"]

def fetch_data(topics):
    combined_raw = []
    seen_titles = set() # 중복 체크용
    
    # 글로벌 메이저 언론사 필터링 쿼리 추가
    major_media = "(site:reuters.com OR site:bloomberg.com OR site:cnn.com OR site:bbc.com OR site:nytimes.com OR site:wsj.com OR site:apnews.com)"

    for topic in topics:
        # [네이버 뉴스 수집]
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=10&sort=sim"
        n_headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
        try:
            n_res = requests.get(n_url, headers=n_headers).json().get('items', [])
            count = 0
            for item in n_res:
                title = clean_text(item['title'])
                short_title = title[:15] # 제목 앞부분만 비교하여 유사 중복 제거
                if short_title in seen_titles or count >= 3: continue
                
                seen_titles.add(short_title)
                combined_raw.append({"source": "국내언론", "title": title, "desc": clean_text(item['description']), "link": item['link']})
                count += 1
        except: pass
        
        # [구글 외신 수집] - 메이저 언론사 필터 적용
        g_query = f"{topic} {major_media}"
        g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
        try:
            g_res = requests.get(g_url, timeout=10)
            root = ET.fromstring(g_res.text)
            count = 0
            for item in root.findall('.//item'):
                title = item.find('title').text
                short_title = title[:15]
                if short_title in seen_titles or count >= 3: continue
                
                seen_titles.add(short_title)
                source = title.split(" - ")[-1] if " - " in title else "Mainstream Media"
                combined_raw.append({"source": source, "title": title, "desc": "", "link": item.find('link').text})
                count += 1
        except: pass
    return combined_raw

if __name__ == "__main__":
    topics = get_target_topics()
    news_list = fetch_data(topics)
    
    # AI 통합 분석 프롬프트
    prompt = f"""
    당신은 글로벌 비즈니스 인사이트 분석가입니다. 아래 데이터를 기반으로 '고위 경영진'을 위한 리포트를 작성하세요.
    
    [분석 주제]: {', '.join(topics)}
    [데이터]: {json.dumps(news_list, ensure_ascii=False)}
    
    [작성 양식]:
    1. 인사이트: 전체 뉴스를 관통하는 핵심 흐름과 국내외 시각 차이를 한국어 한 문장으로 전문적으로 분석.
    2. 뉴스 분석: 중복 없이 핵심 기사만 선별하여 아래 형식 준수.
       - [신문사명] 기사제목
       📌 요약: [한국어 한 문장 요약]
    """
    
    final_report = call_gemini(prompt)

    # 참조 링크 구성 (관리자님 요청 포맷: 신문사 - 한줄 요약 : [url])
    footer = "\n\n🔗 [참조 링크 모음]\n"
    for item in news_list:
        clean_title = item['title'].split(" - ")[0] if " - " in item['title'] else item['title']
        footer += f"- {item['source']} - {clean_title[:35]}... : {item['link']}\n"
        
    today = datetime.now().strftime('%Y-%m-%d')
    msg = MIMEMultipart()
    msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [Premium Insight] {today} - {topics[0]} 외"
    msg.attach(MIMEText(final_report + footer, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
        
    print(f"✅ 리포트 발송 완료 (중복 필터링 및 메이저 언론 우선 적용)")
