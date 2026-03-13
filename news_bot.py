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
    # [핵심 수정] 404 에러 원천 차단: 최신 Gemini 2.0/3 세대용 표준 모델명 사용
    # 구글 API v1beta는 현재 gemini-2.0-flash-exp 또는 gemini-1.5-flash-latest를 권장합니다.
    # 여기서는 가장 호환성이 높은 'gemini-1.5-flash-latest'로 명칭을 보강했습니다.
    model_name = "gemini-1.5-flash-latest" 
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={CONFIG['GEMINI_KEY']}"
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        res_data = response.json()
        
        # 정상 응답 처리
        if 'candidates' in res_data and len(res_data['candidates']) > 0:
            content = res_data['candidates'][0].get('content')
            if content and 'parts' in content:
                return content['parts'][0]['text'].strip()
        
        # 실패 시 상세 로그 (관리자님 확인용)
        error_log = f"⚠️ Gemini 호출 에러 (HTTP {response.status_code})\n"
        error_log += f"- 메시지: {json.dumps(res_data.get('error', res_data))}\n"
        return error_log + "\n(데이터 요약 실패. 하단 링크를 확인하세요.)"

    except Exception as e:
        return f"⚠️ 네트워크 오류: {str(e)}"

def fetch_news(topic):
    news_data = []
    seen = set()
    limit_time = datetime.now() - timedelta(days=3)

    # 네이버 뉴스
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

    # 구글 외신
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
        report_body = "최근 72시간 내 수집된 관련 뉴스가 없습니다."
    else:
        prompt = f"""
        당신은 정세 분석 전문가입니다. 아래 데이터를 바탕으로 한국어로 요약 보고하세요.
        [데이터]: {json.dumps(collected[:15], ensure_ascii=False)}
        
        [양식]:
        📅 {target} 정세 보고
        [Insight]
        핵심 인사이트 한 줄
        
        [뉴스 분석]
        [언론사명] (날짜) 제목
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
    print(f"✅ {today} 보고서 전송 시도 완료")
