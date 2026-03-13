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
        return ["안경 렌즈 산업"]
    except: return ["안경 렌즈 산업"]

def fetch_data(topics):
    combined_raw = []
    seen_titles = set()
    now = datetime.now()
    cutoff_time = now - timedelta(days=3)
    # [핵심] 검색어에 현재 연도를 명시하여 과거 데이터 유입 방지
    current_year = now.year 

    for topic in topics:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=30&sort=date"
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
                
                combined_raw.append({
                    "source": "Pending", "title": title, 
                    "date": pub_date.strftime('%Y-%m-%d %H:%M'), 
                    "link": item.get('originallink') if item.get('originallink') else item['link']
                })
                count += 1
        except: pass
        
        # 외신 검색 시에도 현재 시점(when:3d) 강력 제약
        g_query = f"{topic} industry {now.year} when:3d"
        g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
        try:
            g_res = requests.get(g_url, timeout=15)
            root = ET.fromstring(g_res.text)
            count = 0
            for item in root.findall('.//item'):
                pub_date_str = item.find('pubDate').text
                try: pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z')
                except: pub_date = now
                
                if pub_date < cutoff_time: continue

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
    today_now = datetime.now().strftime('%Y-%m-%d %H:%M')
    topics = get_target_topics()
    news_list = fetch_data(topics)
    
    # [프롬프트 강화] 현재 시점을 엄격히 규정
    prompt = f"""
    당신은 2026년에 근무하는 글로벌 산업 분석 비서입니다. 
    오늘은 {today_now}입니다.
    
    [제공 데이터]: {json.dumps(news_list, ensure_ascii=False)}
    
    [작성 규칙 - 필독]:
    1. 절대 2024년이나 2025년 데이터를 '최근'이라고 언급하지 마세요. 
    2. 오직 제공된 데이터({len(news_list)}건)만 분석하세요. 데이터가 부족하면 부족한 대로 작성하세요.
    3. 제목: 📅 {topics[0]} 산업 분석 보고
    4. [Insight]: 2026년 3월 현재 시점의 핵심 흐름 분석.
    5. [뉴스 본문 분석]: 
       - '[언론사] (게시일자) 제목' 및 '📌 [내용]' 형식 준수.
       - 외신은 반드시 한국어로 번역.
       - 소스가 'Pending'인 경우 도메인을 보고 언론사명을 식별하세요.
    """
    
    final_report = call_gemini(prompt)

    footer = "\n\n🔗 [링크 모음]\n"
    for item in news_list:
        domain = item['link'].split('/')[2].replace('www.', '')
        footer += f"- {item['source'] if item['source'] != 'Pending' else domain} - ({item['date']}) {item['title'][:35]}... : {item['link']}\n"
        
    msg = MIMEMultipart(); msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [7AM Report] {datetime.now().strftime('%Y-%m-%d')} - {topics[0]} 분석"
    msg.attach(MIMEText(final_report + footer, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
    print(f"✅ {today_now} 기준 보고서 발송 완료")
