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
        return ["오늘의 경제 뉴스"]
    except: return ["오늘의 경제 뉴스"]

def fetch_data(topics):
    combined_raw = []
    seen_titles = set()
    
    # [날짜 필터 설정] 오늘 기준 최근 3일 이내
    now = datetime.now()
    three_days_ago = now - timedelta(days=3)
    
    # 글로벌 메이저 외신 쿼리
    major_media = "(site:reuters.com OR site:bloomberg.com OR site:cnn.com OR site:bbc.com OR site:nytimes.com OR site:wsj.com OR site:apnews.com OR site:cnbc.com)"

    for topic in topics:
        # [네이버 뉴스] 정렬 순서를 'date'로 변경하여 최신성 보장
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=30&sort=date"
        n_headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
        try:
            n_res = requests.get(n_url, headers=n_headers, timeout=10).json().get('items', [])
            count = 0
            for item in n_res:
                # 네이버 날짜 형식: "Fri, 13 Mar 2026 10:00:00 +0900"
                pub_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
                if pub_date < three_days_ago: continue # 3일 이전 기사 제외
                
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
        
        # [구글 외신 뉴스] 최근 3일 이내 기사만 검색하도록 쿼리에 'when:3d' 추가
        g_query = f"{topic} {major_media} when:3d"
        g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
        try:
            g_res = requests.get(g_url, timeout=15)
            root = ET.fromstring(g_res.text)
            count = 0
            for item in root.findall('.//item'):
                # 구글 날짜 형식: "Fri, 13 Mar 2026 01:23:45 GMT"
                pub_date_str = item.find('pubDate').text
                pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z')
                if pub_date < three_days_ago: continue
                
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
    
    # 20개 내외의 데이터를 기반으로 정교한 분석 요청
    prompt = f"""
    당신은 글로벌 전략 분석가입니다. 아래 {len(news_list)}개의 최신 뉴스(최근 3일 이내)를 분석하여 리포트를 작성하세요.
    
    [분석 주제]: {', '.join(topics)}
    [데이터]: {json.dumps(news_list, ensure_ascii=False)}
    
    [작성 양식]:
    1. 인사이트: 최근 3일간의 긴박한 흐름을 바탕으로 국내외 보도 차이와 시사점을 전문적으로 분석.
    2. 뉴스 분석: 중복 없이 핵심 기사들을 선정해 아래 형식 준수.
       - [신문사] 기사제목
       📌 요약: [한국어 한 문장 핵심 요약]
    """
    
    final_report = call_gemini(prompt)

    # [참조 링크 모음] 포맷 적용
    footer = "\n\n🔗 [심층 참조 링크 모음 (최근 3일 데이터)]\n"
    for item in news_list:
        clean_title = item['title'].split(" - ")[0] if " - " in item['title'] else item['title']
        footer += f"- {item['source']} - {clean_title[:35]}... : {item['link']}\n"
        
    today = datetime.now().strftime('%Y-%m-%d')
    msg = MIMEMultipart()
    msg['From'] = msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [Deep Insight] {today} - {topics[0]} (최근 3일 집중분석)"
    msg.attach(MIMEText(final_report + footer, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
        
    print(f"✅ 리포트 발송 완료: 최근 3일 이내 기사 {len(news_list)}건 분석")
