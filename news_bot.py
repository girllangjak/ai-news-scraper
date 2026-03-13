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

# 1. 환경 설정
CONFIG = {
    "NAVER": {"ID": os.environ.get("NAVER_ID"), "SEC": os.environ.get("NAVER_SECRET")},
    "MAIL": {"USER": os.environ.get("GMAIL_USER"), "PW": os.environ.get("GMAIL_PW")},
    "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "REPO": "girllangjak/ai-news-scraper"
}

def clean_html(text):
    return re.sub('<.*?>|&([a-z0-9]+|#[0-9]{1,6});', '', text).strip() if text else ""

def get_issue_topic():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}"}
    try:
        res = requests.get(url, headers=headers).json()
        return res[0]['title'] if res else "이란 전쟁"
    except: return "이란 전쟁"

def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_KEY']}"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=120).json()
        # candidates 안전 검사 및 할루시네이션 방지 구조
        if 'candidates' in res and res['candidates']:
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        return "⚠️ AI 분석 엔진이 일시적으로 응답하지 않거나 정책에 의해 제한되었습니다."
    except Exception as e:
        return f"⚠️ 분석 실패 (네트워크 오류: {str(e)[:30]})"

def fetch_news(topic):
    news_data = []
    seen = set()
    now = datetime.now()
    limit_time = now - timedelta(days=3) # 72시간 기준

    # [국내] 네이버 뉴스
    n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=30&sort=date"
    n_headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
    try:
        items = requests.get(n_url, headers=n_headers, timeout=20).json().get('items', [])
        for it in items:
            p_date = datetime.strptime(it['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
            if p_date < limit_time: continue
            title = clean_html(it['title'])
            if title[:15] not in seen:
                seen.add(title[:15])
                news_data.append({
                    "src": "Pending", "title": title, "date": p_date.strftime('%Y-%m-%d'), "link": it['link']
                })
    except: pass

    # [외신] 구글 뉴스 (영어 검색 강제)
    g_query = f"{topic} when:3d"
    g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        root = ET.fromstring(requests.get(g_url, timeout=20).text)
        for it in root.findall('.//item')[:15]:
            title = it.find('title').text
            if title[:15] not in seen:
                seen.add(title[:15])
                src = title.split(" - ")[-1] if " - " in title else "Global"
                news_data.append({
                    "src": src, "title": title.split(" - ")[0], "date": "최근 3일", "link": it.find('link').text
                })
    except: pass
    
    return news_data

if __name__ == "__main__":
    today_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    target = get_issue_topic()
    collected = fetch_news(target)

    # 리포트 생성 로직
    if not collected:
        report_body = "최근 72시간 내에 수집된 관련 뉴스가 없습니다."
    else:
        prompt = f"""
        당신은 2026년 전문 분석 비서입니다. 현재 시각은 {today_str}입니다.
        반드시 제공된 데이터만 사용하여 한국어로 보고서를 작성하세요. 절대 과거 정보를 지어내지 마세요.
        
        [데이터]: {json.dumps(collected, ensure_ascii=False)}
        
        [형식]:
        📅 {target} 산업 분석 보고
        [Insight]
        내용 (한 줄)
        
        [뉴스 본문 분석]
        [실제언론사명] (날짜) 제목
        📌 요약 한 줄 (한국어)
        
        * Pending으로 표기된 국내 언론사는 링크 도메인을 보고 '중앙일보', '뉴시스' 등으로 변환하세요.
        """
        report_body = call_gemini(prompt)

    # 링크 모음 생성
    links = "\n\n🔗 [링크 모음]\n"
    for c in collected:
        domain = c['link'].split('/')[2].replace('www.', '')
        links += f"- {c['src'] if c['src'] != 'Pending' else domain} - ({c['date']}) {c['title'][:40]}... : {c['link']}\n"

    # 메일 전송
    msg = MIMEMultipart()
    msg['Subject'] = f"📅 [7AM Report] {today_str[:10]} - {target} 분석"
    msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
    msg.attach(MIMEText(report_body + links, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
        server.send_mail = server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())

    print(f"✅ {today_str} 보고서 전송 완료")
