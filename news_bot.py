import requests
import smtplib
import os
import xml.etree.ElementTree as ET
import json
import re
import time
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
    # 관리자님 지시사항: gemini-3-flash-preview 모델 사용
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        res = requests.post(url, json=payload, timeout=90)
        res.raise_for_status()
        res_json = res.json()
        return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        return f"⚠️ 분석 엔진 오류 발생. 하단 링크를 참조해 주세요. (Error: {str(e)})"

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
    
    # 글로벌 메이저 외신 쿼리
    major_media = "(site:reuters.com OR site:bloomberg.com OR site:cnn.com OR site:bbc.com OR site:nytimes.com OR site:wsj.com OR site:apnews.com OR site:cnbc.com)"

    for topic in topics:
        # [국내 뉴스 수집]
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=20&sort=date"
        n_headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
        try:
            n_res = requests.get(n_url, headers=n_headers, timeout=10).json().get('items', [])
            for item in n_res:
                pub_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
                if pub_date < cutoff_time: continue
                title = clean_text(item['title'])
                if title[:12] in seen_titles: continue
                seen_titles.add(title[:12])
                
                link = item['link']
                source = "국내언론"
                if "yna.co.kr" in link: source = "연합뉴스"
                elif "hankyung.com" in link: source = "한국경제"
                elif "mk.co.kr" in link: source = "매일경제"
                elif "chosun.com" in link: source = "조선일보"
                
                combined_raw.append({"source": source, "title": title, "date": pub_date.strftime('%Y-%m-%d %H:%M'), "link": link})
        except: pass
        
        # [해외 뉴스 수집 - 영문 키워드 조합]
        g_query = f"{topic} market industry {major_media} when:3d"
        g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
        try:
            g_res = requests.get(g_url, timeout=15)
            root = ET.fromstring(g_res.text)
            for item in root.findall('.//item')[:8]:
                pub_date_str = item.find('pubDate').text
                try: pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z')
                except: pub_date = now
                
                title = item.find('title').text
                if title[:12] in seen_titles: continue
                seen_titles.add(title[:12])
                
                source = title.split(" - ")[-1] if " - " in title else "Global"
                combined_raw.append({"source": source, "title": title.split(" - ")[0], "date": pub_date.strftime('%Y-%m-%d'), "link": item.find('link').text})
        except: pass
        
    return combined_raw

if __name__ == "__main__":
    topics = get_target_topics()
    news_list = fetch_data(topics)
    
    today_date = datetime.now().strftime('%Y-%m-%d')
    
    if not news_list:
        final_content = "최근 3일 내 분석할 새로운 뉴스가 수집되지 않았습니다."
    else:
        # 확정된 메일 구조를 위한 프롬프트 고도화
        prompt = f"""
        당신은 산업 분석 전문가입니다. 아래 뉴스 데이터를 분석하여 관리자 보고용 리포트를 작성하세요.
        반드시 모든 외신 제목과 내용은 한국어로 번역하여 작성하십시오.
        
        [데이터]: {json.dumps(news_list, ensure_ascii=False)}
        
        [작성 양식]:
        📅 {topics[0]} 산업 분석 보고
        
        [Insight]
        (전체 뉴스 흐름을 관통하는 전문적인 인사이트 한 줄)
        
        [뉴스 본문 분석]
        (기사별 형식: [신문사] (게시일자) 번역된 제목)
        📌 (한국어 한 줄 요약)
        """
        final_content = call_gemini(prompt)

    # 🔗 [링크 모음] 섹션 구성
    footer = "\n\n🔗 [링크 모음]\n"
    for item in news_list:
        footer += f"{item['source']} - ({item['date']}) {item['title'][:35]}... : {item['link']}\n\n"
        
    msg = MIMEMultipart()
    msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [7AM Report] {today_date} - {topics[0]} 분석 보고"
    msg.attach(MIMEText(final_content + footer, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
        
    print(f"✅ {today_date} 오전 7시 리포트 발송 완료")