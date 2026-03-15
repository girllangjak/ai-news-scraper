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

# 1. 환경 설정 (GitHub Secrets와 연동)
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
        return res[0]['title'] if res else "정보기술 정세"
    except: return "정보기술 정세"

def call_gemini(prompt):
    """
    Gemini 3 Flash 엔진을 호출하는 최종 안정화 함수
    """
    # 2026년 기준 가장 안정적인 v1beta 경로와 모델명 사용
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_KEY']}"
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        res_data = response.json()
        
        # 정상 응답 추출
        if response.status_code == 200 and 'candidates' in res_data:
            return res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # 에러 발생 시 리포트 본문에 에러 노출
        return f"⚠️ AI 분석 일시적 오류 (HTTP {response.status_code})\n사유: {res_data.get('error', {}).get('message', 'Unknown Error')}"

    except Exception as e:
        return f"⚠️ 시스템 네트워크 오류: {str(e)}"

def fetch_news(topic):
    news_data = []
    seen = set()
    limit_time = datetime.now() - timedelta(days=3)

    # 네이버 뉴스 검색
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
                news_data.append({"src": "네이버뉴스", "title": title, "date": p_date.strftime('%Y-%m-%d'), "link": it['link']})
    except: pass

    # 구글 외신 검색
    g_query = f"{topic} market news when:3d"
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
        당신은 Gemini 3 기반 전문 분석관입니다. 아래 뉴스 데이터를 한국어로 요약하세요.
        
        [데이터]: {json.dumps(collected[:15], ensure_ascii=False)}
        
        [양식]:
        📅 {target} 정세 보고
        [Insight]
        현 정세를 관통하는 핵심 분석 한 줄
        
        [뉴스 분석]
        [언론사명] (날짜) 제목
        📌 핵심 요약 (한국어 한 줄)
        """
        report_body = call_gemini(prompt)

    # 링크 모음 생성
    links = "\n\n🔗 [참조 링크]\n"
    for c in collected:
        links += f"- {c['src']} ({c['date']}): {c['title'][:40]}... > {c['link']}\n"

    # 메일 구성
    msg = MIMEMultipart()
    msg['Subject'] = f"📅 [7AM Report] {today} - {target} 정세 분석"
    msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
    msg.attach(MIMEText(report_body + links, 'plain'))

    # SMTP 전송
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
            server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
        print(f"✅ {today} 보고서 전송 완료")
    except Exception as e:
        print(f"❌ 전송 실패: {e}")
