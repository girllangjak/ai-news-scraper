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
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_KEY']}"
    # 정책을 유지하면서 분석 시도
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    try:
        response = requests.post(url, json=payload, timeout=120)
        res_data = response.json()
        
        # 정상 응답 시
        if 'candidates' in res_data and res_data['candidates'][0].get('content'):
            return res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # 오류 발생 시 상세 사유 추출
        error_info = "⚠️ AI 분석 중단 상세 사유:\n"
        if 'promptFeedback' in res_data:
            fb = res_data['promptFeedback']
            error_info += f"- 차단 사유: {fb.get('blockReason', 'N/A')}\n"
        
        if 'candidates' in res_data and res_data['candidates']:
            ratings = res_data['candidates'][0].get('safetyRatings', [])
            error_info += "- 안전 등급 위반 상세:\n"
            for r in ratings:
                if r.get('probability') != 'NEGLIGIBLE':
                    error_info += f"  * {r['category']}: {r['probability']}\n"
        
        if not 'candidates' in res_data and not 'promptFeedback' in res_data:
            error_info += f"- API 오류 메세지: {json.dumps(res_data)[:200]}\n"
            
        return error_info + "\n(데이터의 민감도가 높아 요약이 거부되었습니다. 원문 링크를 참고하세요.)"
        
    except Exception as e:
        return f"⚠️ 시스템 네트워크 오류: {str(e)}"

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

    g_query = f"{topic} when:3d"
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
        report_body = "최근 수집된 뉴스가 없습니다."
    else:
        prompt = f"""
        당신은 2026년 전문 뉴스 분석관입니다. 제공된 데이터를 한국어로 요약 보고하세요.
        
        [데이터]: {json.dumps(collected[:15], ensure_ascii=False)}
        
        [양식]:
        📅 {target} 분석 보고
        [Insight]
        한 줄 인사이트
        
        [뉴스 분석]
        [언론사] (날짜) 제목
        📌 요약 한 줄
        """
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
    print(f"✅ {today} 디버깅 리포트 전송 완료")
