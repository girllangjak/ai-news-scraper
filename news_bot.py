import requests
import smtplib
import os
import xml.etree.ElementTree as ET
import json
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
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
        res = requests.post(url, json=payload, timeout=60).json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "⚠️ 대량 데이터 분석 중 지연이 발생했습니다. 하단 링크를 참조해 주세요."

def get_target_topics():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            return [t.strip() for t in res[0]['title'].split(',') if t.strip()]
        return ["오늘의 비즈니스 뉴스"]
    except: return ["오늘의 비즈니스 뉴스"]

def fetch_data(topics):
    combined_raw = []
    seen_titles = set()
    
    # [정밀 시점 설정] 실행 시점(오전 7시 가정) 기준 72시간(3일) 이내
    now = datetime.now()
    cutoff_time = now - timedelta(days=3)
    
    major_media = "(site:reuters.com OR site:bloomberg.com OR site:cnn.com OR site:bbc.com OR site:nytimes.com OR site:wsj.com OR site:apnews.com OR site:cnbc.com)"

    for topic in topics:
        # 1. 네이버 뉴스 (최신순 정렬)
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=40&sort=date"
        n_headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
        try:
            n_res = requests.get(n_url, headers=n_headers, timeout=10).json().get('items', [])
            count = 0
            for item in n_res:
                pub_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
                if pub_date < cutoff_time: continue # 3일 필터
                
                title = clean_text(item['title'])
                if title[:12] in seen_titles or count >= 10: continue
                
                seen_titles.add(title[:12])
                link = item['link']
                source = "국내언론"
                if "chosun.com" in link: source = "조선일보"
                elif "joins.com" in link: source = "중앙일보"
                elif "donga.com" in link: source = "동아일보"
                elif "yna.co.kr" in link: source = "연합뉴스"
                elif "hankyung.com" in link: source = "한국경제"
                elif "mk.co.kr" in link: source = "매일경제"
                
                combined_raw.append({"source": source, "title": title, "desc": clean_text(item['description']), "link": link})
                count += 1
        except: pass
        
        # 2. 구글 뉴스 (3일 이내 쿼리)
        g_query = f"{topic} {major_media} when:3d"
        g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
        try:
            g_res = requests.get(g_url, timeout=15)
            root = ET.fromstring(g_res.text)
            count = 0
            for item in root.findall('.//item'):
                pub_date_str = item.find('pubDate').text
                # 구글은 GMT 기준이므로 비교 시 주의
                try:
                    pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z')
                except:
                    pub_date = now # 파싱 실패 시 일단 수집
                
                title = item.find('title').text
                if title[:12] in seen_titles or count >= 10: continue
                
                seen_titles.add(title[:12])
                source = title.split(" - ")[-1] if " - " in title else "Global Media"
                combined_raw.append({"source": source, "title": title, "desc": "", "link": item.find('link').text})
                count += 1
        except: pass
    return combined_raw

if __name__ == "__main__":
    topics = get_target_topics()
    news_list = fetch_data(topics)
    
    prompt = f"""
    당신은 글로벌 전략 컨설턴트입니다. 오전 7시 리포트 브리핑을 준비하세요.
    아래는 지난 3일간 수집된 {len(news_list)}개의 최신 데이터입니다.
    
    [핵심 주제]: {', '.join(topics)}
    [데이터 리스트]: {json.dumps(news_list, ensure_ascii=False)}
    
    [브리핑 가이드]:
    1. 인사이트: 3일간의 흐름 중 결정적인 비즈니스 변수와 국내외 시각 차이를 한 문장으로 분석.
    2. 주요 뉴스 요약: 중요도 순으로 기사를 선별하여 아래 형식 준수.
       - [신문사] 기사제목
       📌 요약: [한국어 한 문장 핵심 요약]
    """
    
    final_report = call_gemini(prompt)

    # 3. 메일 구성 및 발송
    today_str = datetime.now().strftime('%Y-%m-%d')
    footer = f"\n\n🔗 [오전 7시 기준 심층 참조 링크 모음]\n"
    for item in news_list:
        clean_title = item['title'].split(" - ")[0] if " - " in item['title'] else item['title']
        footer += f"- {item['source']} - {clean_title[:35]}... : {item['link']}\n"
        
    msg = MIMEMultipart()
    msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [7AM Report] {today_str} - {topics[0]} 집중분석"
    msg.attach(MIMEText(final_report + footer, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
        
    print(f"✅ 오전 7시 정기 리포트 발송 완료 ({len(news_list)}건 분석)")
