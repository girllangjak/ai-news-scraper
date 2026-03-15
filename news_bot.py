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

# 1. 시스템 설정
CONFIG = {
    "NAVER": {"ID": os.environ.get("NAVER_ID"), "SEC": os.environ.get("NAVER_SECRET")},
    "MAIL": {"USER": os.environ.get("GMAIL_USER"), "PW": os.environ.get("GMAIL_PW")},
    "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "REPO": "girllangjak/ai-news-scraper"
}

# 공신력 있는 Tier 1 외신 리스트
TIER1_DOMAINS = ["reuters.com", "bloomberg.com", "wsj.com", "ft.com", "apnews.com", "nytimes.com", "economist.com", "theverge.com", "techcrunch.com"]

def clean_html(text):
    return re.sub('<.*?>|&([a-z0-9]+|#[0-9]{1,6});', '', text).strip() if text else ""

def get_issue_topic():
    """GitHub Issues 제목을 키워드로 가져옴"""
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}"}
    try:
        res = requests.get(url, headers=headers).json()
        return res[0]['title'] if isinstance(res, list) and len(res) > 0 else None
    except: return None

def call_gemini(prompt):
    """
    [수정 완료] 404 에러 원인인 모델명을 'gemini-1.5-flash-002'로 정밀 지정함.
    오류 발생 시 기술 정보만 정밀 보고함.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-002:generateContent?key={CONFIG['GEMINI_KEY']}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        res_data = response.json()
        
        if response.status_code == 200 and 'candidates' in res_data:
            return res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # [오류 대응 프로토콜] 상세 기술 정보만 보고
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
    """중복 제거 및 최대 10개 기사 추출 로직"""
    news_data = {"KR": [], "Global": []}
    seen_titles = set()
    limit_time = datetime.now() - timedelta(days=3)

    # [국내] 네이버 뉴스 검색 (5개 목표)
    n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=25&sort=date"
    n_headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
    try:
        items = requests.get(n_url, headers=n_headers, timeout=20).json().get('items', [])
        for it in items:
            title = clean_html(it['title'])
            # 제목 앞 15자 유사도 검사로 중복 제거
            if title[:15] not in seen_titles and len(news_data["KR"]) < 5:
                seen_titles.add(title[:15])
                news_data["KR"].append({"src": "국내언론", "title": title, "link": it['link']})
    except: pass

    # [해외] 공신력 외신 검색 (5개 목표)
    g_query = f"{topic} (" + " OR ".join([f"site:{d}" for d in TIER1_DOMAINS]) + ") when:3d"
    g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        root = ET.fromstring(requests.get(g_url, timeout=20).text)
        for it in root.findall('.//item'):
            title = it.find('title').text
            if title[:15] not in seen_titles and len(news_data["Global"]) < 5:
                seen_titles.add(title[:15])
                src = title.split(" - ")[-1] if " - " in title else "Tier 1 Media"
                news_data["Global"].append({"src": src, "title": title.split(" - ")[0], "link": it.find('link').text})
    except: pass
    
    return news_data

if __name__ == "__main__":
    today = datetime.now().strftime('%Y-%m-%d')
    target = get_issue_topic()

    if not target:
        print("GitHub Issues에 활성화된 키워드가 없습니다.")
    else:
        news = fetch_news(target)
        all_news = news["KR"] + news["Global"]
        
        if not all_news:
            report_body = f"🔎 '{target}'에 대한 최근 3일간의 유효 기사가 없습니다."
        else:
            # 분석 프롬프트: 국내/해외 분리 및 차이점 분석 지시
            prompt = f"""
            지침: 다음 뉴스 데이터를 바탕으로 '{target}' 정세를 한국어로 요약 분석하라.
            1. 해외 기사는 한국어로 번역하여 핵심을 파악할 것.
            2. 국내와 해외의 관점 차이를 반드시 비교할 것.
            
            데이터: {json.dumps(all_news, ensure_ascii=False)}
            
            양식:
            📅 [Insight]: 전체 흐름을 관통하는 한 줄 분석
            
            [국내 정세]: (국내 소식 요약)
            - 기사제목: 핵심 내용
            
            [해외 정세]: (Tier 1 외신 분석)
            - 기사제목: 핵심 내용
            
            [국내외 차이 분석]: 국내와 해외의 시각 차이, 시장 온도, 진행 속도 비교
            """
            report_body = call_gemini(prompt)

        # 링크 모음 (Reference)
        links = "\n\n🔗 [Reference]\n" + "\n".join([f"- {n['src']}: {n['link']}" for n in all_news])
        
        # 메일 발송 구성
        msg = MIMEMultipart()
        msg['Subject'] = f"📅 [Global Analysis] {today} - {target}"
        msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
        msg.attach(MIMEText(report_body + links, 'plain'))

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
                server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
            print(f"✅ {today} 리포트 전송 성공")
        except Exception as e:
            print(f"❌ 메일 전송 실패: {e}")
