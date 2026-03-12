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
        res = requests.post(url, json=payload, timeout=60).json() # 대량 분석을 위해 타임아웃 연장
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "⚠️ 대량 데이터 분석 중 지연이 발생했습니다. 링크를 참조해 주세요."

def get_target_topics():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            return [t.strip() for t in res[0]['title'].split(',') if t.strip()]
        return ["오늘의 경제 뉴스"]
    except: return ["오늘의 경제 뉴스"]

def fetch_data(topics):
    combined_raw = []
    seen_titles = set()
    # 신뢰도 높은 글로벌 외신 리스트
    major_media = "(site:reuters.com OR site:bloomberg.com OR site:cnn.com OR site:bbc.com OR site:nytimes.com OR site:wsj.com OR site:apnews.com OR site:cnbc.com OR site:ft.com)"

    for topic in topics:
        # [국내 뉴스 수집 - 최대 10개 시도]
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=20&sort=sim"
        n_headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
        try:
            n_res = requests.get(n_url, headers=n_headers).json().get('items', [])
            count = 0
            for item in n_res:
                title = clean_text(item['title'])
                # 제목 앞 12자 비교로 중복 제거
                if title[:12] in seen_titles or count >= 10: continue
                
                seen_titles.add(title[:12])
                # 링크를 통한 언론사 유추 (naver.com이 아닌 원문 링크에서 추출)
                link = item['link']
                source = "국내언론"
                if "chosun.com" in link: source = "조선일보"
                elif "joins.com" in link: source = "중앙일보"
                elif "donga.com" in link: source = "동아일보"
                elif "hani.co.kr" in link: source = "한겨레"
                elif "yna.co.kr" in link: source = "연합뉴스"
                elif "hankyung.com" in link: source = "한국경제"
                elif "mk.co.kr" in link: source = "매일경제"
                
                combined_raw.append({"source": source, "title": title, "desc": clean_text(item['description']), "link": link})
                count += 1
        except: pass
        
        # [외신 뉴스 수집 - 최대 10개 시도]
        g_query = f"{topic} {major_media}"
        g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
        try:
            g_res = requests.get(g_url, timeout=15)
            root = ET.fromstring(g_res.text)
            count = 0
            for item in root.findall('.//item'):
                title = item.find('title').text
                if title[:12] in seen_titles or count >= 10: continue
                
                seen_titles.add(title[:12])
                source = title.split(" - ")[-1] if " - " in title else "Mainstream"
                combined_raw.append({"source": source, "title": title, "desc": "", "link": item.find('link').text})
                count += 1
        except: pass
    return combined_raw

if __name__ == "__main__":
    topics = get_target_topics()
    news_list = fetch_data(topics)
    
    # 10개 이상의 데이터를 처리하기 위한 정교한 프롬프트
    prompt = f"""
    당신은 글로벌 전략 컨설턴트입니다. 아래 {len(news_list)}개의 방대한 뉴스 데이터를 분석하여 핵심만 요약하세요.
    
    [주제]: {', '.join(topics)}
    [데이터]: {json.dumps(news_list, ensure_ascii=False)}
    
    [작성 가이드]:
    1. 인사이트: 국내외 보도의 결정적인 시각 차이와 비즈니스 시사점을 전문적으로 요약.
    2. 핵심 기사 분석: 중복을 제외하고 가장 가치 있는 기사들을 선정해 아래 형식으로 작성.
       - [신문사] 기사제목
       📌 요약: [한국어 한 문장 핵심 요약]
    """
    
    final_report = call_gemini(prompt)

    # [참조 링크 모음 최적화] - 관리자님 요청 포맷 적용
    footer = "\n\n🔗 [심층 참조 링크 모음 (최대 20건)]\n"
    for item in news_list:
        clean_title = item['title'].split(" - ")[0] if " - " in item['title'] else item['title']
        footer += f"- {item['source']} - {clean_title[:35]}... : {item['link']}\n"
        
    today = datetime.now().strftime('%Y-%m-%d')
    msg = MIMEMultipart()
    msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [Deep Insight] {today} - {topics[0]} 분석"
    msg.attach(MIMEText(final_report + footer, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
        
    print(f"✅ 리포트 발송 완료: 총 {len(news_list)}건의 자료 분석")
