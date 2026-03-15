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

# 1. 2026년 최신 모델 리스트 (우선순위 순)
MODEL_PRIORITY = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-1.5-flash-latest"]

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
        return res[0]['title'] if isinstance(res, list) and len(res) > 0 else None
    except: return None

def call_gemini(prompt):
    """
    [완결판] 사용 가능한 모델을 순차적으로 시도하여 404를 원천 봉쇄함.
    실패 시에는 기술적 디버깅 정보만 극도로 상세히 메일링함.
    """
    last_error = ""
    for model in MODEL_PRIORITY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={CONFIG['GEMINI_KEY']}"
        headers = {'Content-Type': 'application/json'}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            res_data = response.json()
            if response.status_code == 200:
                return res_data['candidates'][0]['content']['parts'][0]['text'].strip(), True
            last_error = f"Model {model} failed: {json.dumps(res_data)}"
        except Exception as e:
            last_error = str(e)
            continue

    # 모든 모델 실패 시 상세 리포트 생성
    error_report = [
        "🚨 [ULTIMATE DEBUG REPORT - ALL MODELS FAILED]",
        f"TIMESTAMP: {datetime.now().isoformat()}",
        f"TRIED_MODELS: {MODEL_PRIORITY}",
        f"LAST_RESPONSE: {last_error}",
        "CHECK_LIST: 1. API_KEY valid? 2. Billing enabled? 3. Regional restriction?"
    ]
    return "\n".join(error_report), False

def fetch_news(topic):
    # (기존 뉴스 수집 로직과 동일하되, 중복 제거 강화)
    news_data = {"KR": [], "Global": []}
    seen_titles = set()
    limit_time = datetime.now() - timedelta(days=3)

    # 국내 (네이버)
    n_headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
    n_res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=20", headers=n_headers).json()
    for it in n_res.get('items', []):
        title = clean_html(it['title'])
        if title[:15] not in seen_titles and len(news_data["KR"]) < 5:
            seen_titles.add(title[:15]); news_data["KR"].append({"src": "국내", "title": title, "link": it['link']})

    # 해외 (구글 뉴스 RSS + 공신력 필터)
    domains = " OR ".join([f"site:{d}" for d in ["reuters.com", "bloomberg.com", "wsj.com", "ft.com"]])
    g_url = f"https://news.google.com/rss/search?q={quote(topic + ' ' + domains)}&hl=en-US"
    root = ET.fromstring(requests.get(g_url).text)
    for it in root.findall('.//item')[:15]:
        title = it.find('title').text
        if title[:15] not in seen_titles and len(news_data["Global"]) < 5:
            seen_titles.add(title[:15]); news_data["Global"].append({"src": "외신", "title": title, "link": it.find('link').text})
    
    return news_data

if __name__ == "__main__":
    target = get_issue_topic()
    if target:
        news = fetch_news(target)
        all_items = news["KR"] + news["Global"]
        if all_items:
            # 분석 요청
            res_text, success = call_gemini(f"Analyze these news about '{target}': {json.dumps(all_items, ensure_ascii=False)}")
            
            # 이메일 발송
            msg = MIMEMultipart()
            msg['Subject'] = f"{'📅' if success else '🚨'} News Report: {target}"
            msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
            
            # 실패 시 리포트만, 성공 시 분석+참조링크
            body = res_text if not success else f"{res_text}\n\n🔗 [Reference]\n" + "\n".join([f"- {n['title']}: {n['link']}" for n in all_items])
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
                server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
