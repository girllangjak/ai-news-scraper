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
    """HTML 태그 및 특수문자 정제"""
    if not text: return ""
    return re.sub('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});', '', text).strip()

def call_gemini(prompt):
    """Gemini API 통합 분석 호출"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, timeout=40).json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "⚠️ 분석 엔진 응답 지연으로 요약을 생성하지 못했습니다."

def get_target_topics():
    """GitHub 이슈에서 키워드 추출 (콤마 구분)"""
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        if isinstance(res, list) and len(res) > 0:
            return [t.strip() for t in res[0]['title'].split(',') if t.strip()]
        return ["오늘의 주요 뉴스"]
    except: return ["오늘의 주요 뉴스"]

def fetch_data(topics):
    """네이버 및 구글 뉴스 원천 데이터 수집"""
    combined_raw = []
    for topic in topics:
        # 네이버 뉴스
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=3&sort=sim"
        n_headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
        try:
            n_res = requests.get(n_url, headers=n_headers, timeout=10).json().get('items', [])
            for item in n_res:
                combined_raw.append({
                    "source": "국내언론", 
                    "title": clean_text(item['title']), 
                    "desc": clean_text(item['description']), 
                    "link": item['link']
                })
        except: pass
        
        # 구글 뉴스 (영어)
        g_url = f"https://news.google.com/rss/search?q={quote(topic)}&hl=en-US&gl=US&ceid=US:en"
        try:
            g_res = requests.get(g_url, timeout=10)
            root = ET.fromstring(g_res.text)
            for item in root.findall('.//item')[:3]:
                title = item.find('title').text
                # 구글 뉴스는 '제목 - 신문사' 형식이 많으므로 분리 시도
                source = "외신"
                if " - " in title:
                    source = title.split(" - ")[-1]
                combined_raw.append({
                    "source": source, 
                    "title": title, 
                    "desc": "", 
                    "link": item.find('link').text
                })
        except: pass
    return combined_raw

if __name__ == "__main__":
    # 1. 키워드 로드
    topics = get_target_topics()
    
    # 2. 뉴스 수집
    news_list = fetch_data(topics)
    
    # 3. 통합 분석 프롬프트 (요약본을 포함한 결과 생성 요청)
    prompt = f"""
    당신은 전문 뉴스 분석가입니다. 아래 데이터를 기반으로 리포트를 작성하세요.
    
    [분석 주제]: {', '.join(topics)}
    [데이터]: {json.dumps(news_list, ensure_ascii=False)}
    
    [작성 양식]:
    1. 인사이트: 전체 뉴스를 관통하는 국내외 시각 차이를 한국어 한 문장으로 분석.
    2. 뉴스 본문 분석: 각 기사별로 아래 형식을 지킬 것.
       - [신문사] 기사제목
       📌 요약: [한국어 한 문장 핵심 요약]
    """
    
    final_report = call_gemini(prompt)

    # 4. 참조 링크 섹션 재구성 (관리자님 요청: 참조한 신문사 - 한줄 요약 : [url])
    # AI에게 요약문을 다시 추출하기보다, AI가 생성한 본문에서 요약부분을 가져오는 것이 정확하지만
    # 구조적 안정성을 위해 제목과 링크를 매칭하여 출력합니다.
    footer = "\n\n🔗 [참조 링크 모음]\n"
    for item in news_list:
        # AI가 분석한 요약을 가져올 수 없으므로 제목을 활용해 링크 섹션 구성
        footer += f"- {item['source']} - {item['title'][:40]}... : {item['link']}\n"
        
    # 5. 메일 구성 및 발송
    today = datetime.now().strftime('%Y-%m-%d')
    msg = MIMEMultipart()
    msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [글로벌 리포트] {today} - {topics[0]} 외"
    msg.attach(MIMEText(final_report + footer, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
        
    print(f"✅ 리포트 발송 완료: {len(topics)}개 주제 분석")
