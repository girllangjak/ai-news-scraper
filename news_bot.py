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

# 1. 환경 설정 및 공신력 외신 리스트
CONFIG = {
    "NAVER": {"ID": os.environ.get("NAVER_ID"), "SEC": os.environ.get("NAVER_SECRET")},
    "MAIL": {"USER": os.environ.get("GMAIL_USER"), "PW": os.environ.get("GMAIL_PW")},
    "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "REPO": "girllangjak/ai-news-scraper"
}

TIER1_DOMAINS = ["reuters.com", "bloomberg.com", "wsj.com", "ft.com", "apnews.com", "nytimes.com", "economist.com", "theverge.com", "techcrunch.com"]

def clean_html(text):
    return re.sub('<.*?>|&([a-z0-9]+|#[0-9]{1,6});', '', text).strip() if text else ""

def get_issue_topic():
    """GitHub Issues에서만 제목을 가져옴"""
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}"}
    try:
        res = requests.get(url, headers=headers).json()
        return res[0]['title'] if isinstance(res, list) and len(res) > 0 else None
    except: return None

def call_gemini(prompt):
    """Gemini 3 Flash 호출 및 정밀 오류 보고 로직"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_KEY']}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        res_data = response.json()
        
        if response.status_code == 200 and 'candidates' in res_data:
            return res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # [오류 대응 프로토콜] 상세 기술 정보만 구성
        error_log = [
            "❌ [Gemini API Debug Report]",
            f"- HTTP Status: {response.status_code}",
            f"- Endpoint: {url.split('?')[0]}",
            "- Full Response Payload:",
            json.dumps(res_data, indent=2, ensure_ascii=False),
            "-------------------------------------------"
        ]
        return "\n".join(error_log)
    except Exception as e:
        return f"❌ System Critical Error: {str(e)}"

def fetch_news(topic):
    """중복 제거 및 공신력 필터링 기반 뉴스 수집 (최대 10개)"""
    news_data = {"KR": [], "Global": []}
    seen_titles = set()
    limit_time = datetime.now() - timedelta(days=3)

    # [국내] 네이버 검색 (5개 목표)
    n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=20&sort=date"
    n_headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
    try:
        items = requests.get(n_url, headers=n_headers, timeout=20).json().get('items', [])
        for it in items:
            p_date = datetime.strptime(it['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
            title = clean_html(it['title'])
            # 중복 제거 (제목 유사성 15자 기준)
            if p_date > limit_time and title[:15] not in seen_titles and len(news_data["KR"]) < 5:
                seen_titles.add(title[:15])
                news_data["KR"].append({"src": "국내언론", "title": title, "link": it['link']})
    except: pass

    # [해외] 구글 뉴스 (공신력 미디어 필터링, 5개 목표)
    # 영어 키워드 검색을 위해 topic을 쿼리에 포함 (AI가 분석 단계에서 번역 수행)
    g_query = f"{topic} (" + " OR ".join([f"site:{d}" for d in TIER1_DOMAINS]) + ") when:3d"
    g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        root = ET.fromstring(requests.get(g_url, timeout=20).text)
        for it in root.findall('.//item'):
            title = it.find('title').text
            link = it.find('link').text
            if title[:15] not in seen_titles and len(news_data["Global"]) < 5:
                seen_titles.add(title[:15])
                src = title.split(" - ")[-1] if " - " in title else "Tier 1 Media"
                news_data["Global"].append({"src": src, "title": title.split(" - ")[0], "link": link})
    except: pass
    
    return news_data

if __name__ == "__main__":
    today = datetime.now().strftime('%Y-%m-%d')
    target = get_issue_topic()

    if not target:
        print("이슈가 없습니다. 실행을 종료합니다.")
    else:
        news = fetch_news(target)
        all_news = news["KR"] + news["Global"]
        
        if not all_news:
            report_body = f"🔎 '{target}'에 대한 최근 3일간의 기사를 찾을 수 없습니다."
        else:
            prompt = f"""
            [지침]: 이슈 '{target}'에 대해 국내외 기사를 분석하라. 해외 기사는 한국어로 번역하여 처리하라.
            
            [데이터]: {json.dumps(all_news, ensure_ascii=False)}
            
            [리포트 양식]:
            📅 [Insight]: 전체 정세를 관통하는 핵심 분석 한 줄
            
            [국내 정세]: (국내 뉴스 요약)
            - 기사제목: 요약 한 줄
            
            [해외 정세]: (Tier 1 외신 요약 및 번역)
            - 기사제목: 요약 한 줄
            
            [국내외 차이 분석]: 국내와 해외의 시각 차이, 시장 온도, 기술 속도 비교 정리
            """
            report_body = call_gemini(prompt)

        # 링크 모음 (Reference)
        links = "\n\n🔗 [Reference]\n" + "\n".join([f"- {n['src']}: {n['link']}" for n in all_news])
        
        # 메일 발송
        msg = MIMEMultipart()
        msg['Subject'] = f"📅 [Global Analysis] {today} - {target}"
        msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
        msg.attach(MIMEText(report_body + links, 'plain'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
            server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
        print(f"✅ 완료: {target}")
