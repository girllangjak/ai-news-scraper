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
    # 타임아웃 120초로 연장하여 '응답 지연' 방지
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, timeout=120).json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        return f"⚠️ 분석 엔진 연결 실패 (사유: {str(e)[:50]})\n하단 링크를 직접 확인해 주세요."

def get_target_topics():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            return [t.strip() for t in res[0]['title'].split(',') if t.strip()]
        return ["안경 컬러콘택트렌즈"]
    except: return ["안경 컬러콘택트렌즈"]

def fetch_data(topics):
    combined_raw = []
    seen_titles = set()
    now = datetime.now()
    cutoff_time = now - timedelta(days=3)

    for topic in topics:
        # 네이버 뉴스 (최신순)
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=20&sort=date"
        n_headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
        try:
            n_res = requests.get(n_url, headers=n_headers, timeout=20).json().get('items', [])
            for item in n_res:
                pub_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
                if pub_date < cutoff_time: continue
                title = clean_text(item['title'])
                if title[:15] in seen_titles: continue
                seen_titles.add(title[:15])
                combined_raw.append({
                    "source": "Pending", "title": title, "date": pub_date.strftime('%Y-%m-%d %H:%M'), 
                    "link": item.get('originallink') if item.get('originallink') else item['link']
                })
        except: pass
        
        # 구글 외신 (최신순)
        g_query = f"{topic} market when:3d"
        g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
        try:
            g_res = requests.get(g_url, timeout=20)
            root = ET.fromstring(g_res.text)
            for item in root.findall('.//item'):
                title = item.find('title').text
                if title[:15] in seen_titles: continue
                seen_titles.add(title[:15])
                source = title.split(" - ")[-1] if " - " in title else "Global"
                combined_raw.append({
                    "source": source, "title": title.split(" - ")[0], "date": "최근 3일 이내", 
                    "link": item.find('link').text
                })
        except: pass
    return combined_raw

if __name__ == "__main__":
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    topics = get_target_topics()
    news_list = fetch_data(topics)
    
    if not news_list:
        final_report = "검색된 최근 3일간의 새로운 뉴스가 없습니다."
    else:
        prompt = f"""
        당신은 산업 분석 비서입니다. 현재 시각은 {current_time}입니다.
        
        [지시사항]:
        1. 반드시 제공된 데이터만 사용하세요. 절대 과거 지식을 지어내지 마세요.
        2. 양식:
           📅 {topics[0]} 산업 분석 보고
           [Insight]
           인사이트 한 줄 (한국어)
           
           [뉴스 본문 분석]
           [언론사명] (게시일자) 제목
           📌 [한국어 요약 한 줄]
        
        [데이터]: {json.dumps(news_list, ensure_ascii=False)}
        """
        final_report = call_gemini(prompt)

    footer = "\n\n🔗 [링크 모음]\n"
    for item in news_list:
        domain = item['link'].split('/')[2].replace('www.', '')
        footer += f"- {item['source'] if item['source'] != 'Pending' else domain} - {item['title'][:40]}... : {item['link']}\n"
        
    msg = MIMEMultipart(); msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [7AM Report] {current_time[:10]} - 분석 보고"
    msg.attach(MIMEText(final_report + footer, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
