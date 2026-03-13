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
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, timeout=60).json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "⚠️ 분석 엔진 응답 지연이 발생했습니다."

def get_target_topics():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            return [t.strip() for t in res[0]['title'].split(',') if t.strip()]
        return ["안경 산업"]
    except: return ["안경 산업"]

def fetch_data(topics):
    combined_raw = []
    seen_titles = set()
    now = datetime.now()
    cutoff_time = now - timedelta(days=3)
    major_media = "(site:reuters.com OR site:bloomberg.com OR site:cnn.com OR site:bbc.com OR site:nytimes.com OR site:wsj.com OR site:apnews.com OR site:cnbc.com)"

    for topic in topics:
        # [국내 뉴스] 최신순 10개
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=20&sort=date"
        n_headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
        try:
            n_res = requests.get(n_url, headers=n_headers, timeout=10).json().get('items', [])
            count = 0
            for item in n_res:
                pub_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
                if pub_date < cutoff_time: continue
                title = clean_text(item['title'])
                if title[:12] in seen_titles or count >= 10: continue
                seen_titles.add(title[:12])
                
                link = item['link']
                source = "국내언론"
                if "yna.co.kr" in link: source = "연합뉴스"
                elif "hankyung.com" in link: source = "한국경제"
                elif "mk.co.kr" in link: source = "매일경제"
                elif "chosun.com" in link: source = "조선일보"
                
                combined_raw.append({
                    "source": source, "title": title, 
                    "date": pub_date.strftime('%Y-%m-%d %H:%M'), "link": link
                })
                count += 1
        except: pass
        
        # [해외 뉴스] 영문 키워드 전환 및 최신순 10개
        # AI를 쓰지 않고 간단한 키워드 추가로 영문 검색 유도
        g_query = f"{topic} market industry {major_media} when:3d"
        g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
        try:
            g_res = requests.get(g_url, timeout=15)
            root = ET.fromstring(g_res.text)
            count = 0
            for item in root.findall('.//item'):
                pub_date_str = item.find('pubDate').text
                try: pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z')
                except: pub_date = now
                
                title = item.find('title').text
                if title[:12] in seen_titles or count >= 10: continue
                seen_titles.add(title[:12])
                
                source = title.split(" - ")[-1] if " - " in title else "Global"
                combined_raw.append({
                    "source": source, "title": title.split(" - ")[0], 
                    "date": pub_date.strftime('%Y-%m-%d'), "link": item.find('link').text
                })
                count += 1
        except: pass
    return combined_raw

if __name__ == "__main__":
    topics = get_target_topics()
    news_list = fetch_data(topics)
    
    # [인사이트 및 번역 요약 생성]
    prompt = f"""
    당신은 글로벌 산업 분석가입니다. 아래 뉴스 데이터를 분석하여 관리자 보고용 리포트를 작성하세요.
    
    [데이터]: {json.dumps(news_list, ensure_ascii=False)}
    
    [작성 양식]:
    1. 📅 [주제] 산업 분석 보고
    2. [Insight]: 전체 흐름을 관통하는 전문적인 인사이트 한 줄 (한국어).
    3. [뉴스 본문 분석]: 
       - 기사별로 '[신문사] (게시일자) 제목' 형식 준수. 
       - 제목과 요약은 반드시 한국어로 번역해서 작성.
       - 요약은 '📌 [내용]' 형식으로 작성.
    """
    
    final_report = call_gemini(prompt)

    # [링크 모음 구성]
    footer = "\n\n🔗 [링크 모음]\n"
    for item in news_list:
        # 링크 섹션도 제목을 한글로 노출하기 위해 AI 분석 결과와 매칭이 필요하나, 
        # 안정성을 위해 원문 제목을 짧게 자르고 링크를 붙입니다.
        footer += f"- {item['source']} - ({item['date']}) {item['title'][:35]}... : {item['link']}\n"
        
    # 메일 발송
    msg = MIMEMultipart(); msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [7AM Report] {datetime.now().strftime('%Y-%m-%d')} - {topics[0]} 분석"
    msg.attach(MIMEText(final_report + footer, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
    print("✅ 보고서 구조화 및 발송 완료")
