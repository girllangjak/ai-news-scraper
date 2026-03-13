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
    # [마지막 수단] 가장 안정적인 모델명 2개를 순차적으로 시도합니다.
    # 1. gemini-1.5-flash (정식 버전)
    # 2. gemini-pro (기존 표준 버전)
    models_to_try = ["gemini-1.5-flash", "gemini-pro"]
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    last_error = ""
    for model in models_to_try:
        # 정식 v1 API 경로 사용
        url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={CONFIG['GEMINI_KEY']}"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            res_data = response.json()
            
            if response.status_code == 200 and 'candidates' in res_data:
                return res_data['candidates'][0]['content']['parts'][0]['text'].strip()
            
            last_error = f"Model {model} 실패: {res_data.get('error', {}).get('message', 'Unknown Error')}"
        except Exception as e:
            last_error = str(e)
            continue

    # 모든 모델 시도 실패 시 상세 정보 반환
    return f"⚠️ 모든 모델 호출 실패. 마지막 에러: {last_error}\nAPI 키 권한 또는 모델 가용성을 확인해 주세요."

def fetch_news(topic):
    news_data = []
    seen = set()
    limit_time = datetime.now() - timedelta(days=3)

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
                news_data.append({"src": "Pending", "title": title, "date": p_date.strftime('%Y-%m-%d'), "link": it['link']})
    except: pass

    g_query = f"{topic} news when:3d"
    g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        root = ET.fromstring(requests.get(g_url, timeout=20).text)
        for it in root.findall('.//item')[:10]:
            title = it.find('title').text
            if title[:15] not in seen:
                seen.add(title[:15])
                src = title.split(" - ")[-1] if " - " in title else "Global"
                news_data.append({"src": src, "title": title.split(" - ")[0], "date": "최근 3일", "link": it.find('link').text})
    except: pass
    
    return news_data

if __name__ == "__main__":
    today = datetime.now().strftime('%Y-%m-%d')
    target = get_issue_topic()
    collected = fetch_news(target)

    if not collected:
        report_body = "최근 수집된 기사가 없습니다."
    else:
        prompt = f"당신은 전문 분석관입니다. 아래 뉴스를 한국어로 요약 보고하세요.\n{json.dumps(collected[:15], ensure_ascii=False)}"
        report_body = call_gemini(prompt)

    links = "\n\n🔗 [링크 모음]\n"
    for c in collected:
        domain = c['link'].split('/')[2].replace('www.', '')
        links += f"- {c['src'] if c['src'] != 'Pending' else domain} - ({c['date']}) {c['title'][:45]}... : {c['link']}\n"

    msg = MIMEMultipart()
    msg['Subject'] = f"📅 [7AM Report] {today} - {target} 분석"
    msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
    msg.attach(MIMEText(report_body + links, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
        server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
    print(f"✅ {today} 전송 시도 완료")
