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

# 모델 우선순위 유지
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
    """지침: 반드시 한국어로 응답하도록 프롬프트 제어 강화"""
    for model in MODEL_PRIORITY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={CONFIG['GEMINI_KEY']}"
        headers = {'Content-Type': 'application/json'}
        # 응답 언어를 한국어로 고정하는 시스템 지침 추가
        payload = {
            "contents": [{"parts": [{"text": f"너는 전문 뉴스 분석가야. 반드시 한국어로만 응답해. 지침: {prompt}"}]}],
            "generationConfig": {"temperature": 0.2, "topP": 0.8} # 요약 품질을 위해 창의성 낮춤
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=40)
            res_data = response.json()
            if response.status_code == 200:
                return res_data['candidates'][0]['content']['parts'][0]['text'].strip(), True
        except: continue
    return "API 호출 실패", False

def fetch_news(topic):
    """
    1. 검색 범위를 '3일 이내'로 강제 제한
    2. 무관한 뉴스 배제를 위해 키워드 조합 최적화
    """
    news_data = {"KR": [], "Global": []}
    seen_titles = set()
    # 날짜 기준 설정 (3일 전)
    days_3_ago = datetime.now() - timedelta(days=3)

    # [국내] 네이버: 정렬을 'sim'이 아닌 'date'로 고정하여 최신성 확보
    n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=30&sort=date"
    n_headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
    try:
        items = requests.get(n_url, headers=n_headers, timeout=20).json().get('items', [])
        for it in items:
            p_date = datetime.strptime(it['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
            title = clean_html(it['title'])
            # 3일 이내 기사만 통과
            if p_date > days_3_ago and title[:15] not in seen_titles and len(news_data["KR"]) < 5:
                seen_titles.add(title[:15])
                news_data["KR"].append({"src": "국내", "title": title, "link": it['link']})
    except: pass

    # [해외] 구글 뉴스: 쿼리 필터링 강화 (3일 이내 & 키워드 매칭)
    # 기사 내용에 'lens'나 'k-beauty'가 포함되도록 쿼리 보정
    g_query = f'"{topic}" (lens OR brand OR model) when:3d'
    g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        root = ET.fromstring(requests.get(g_url, timeout=20).text)
        for it in root.findall('.//item'):
            title = it.find('title').text
            # 구글 RSS의 pubDate 파싱 및 필터링
            g_pub_date = datetime.strptime(it.find('pubDate').text, '%a, %d %b %Y %H:%M:%S GMT')
            if g_pub_date > (days_3_ago - timedelta(hours=9)) and title[:15] not in seen_titles and len(news_data["Global"]) < 5:
                seen_titles.add(title[:15])
                news_data["Global"].append({"src": "외신", "title": title.split(" - ")[0], "link": it.find('link').text})
    except: pass
    
    return news_data

if __name__ == "__main__":
    target = get_issue_topic()
    if target:
        news = fetch_news(target)
        all_items = news["KR"] + news["Global"]
        if all_items:
            # 상세 분석 지침 (한국어 고정 및 요약 수준 상향)
            prompt = f"""
            주제 '{target}'에 대해 수집된 다음 기사들을 분석하라.
            지침:
            1. 반드시 '한국어'로 작성할 것.
            2. 단순 나열이 아닌, 국내와 해외의 시각 차이를 중심으로 심층 분석할 것.
            3. 각 섹션별로 3문장 이상의 구체적인 요약을 제공할 것.
            4. 관련 없는 기사는 분석에서 제외할 것.
            
            데이터: {json.dumps(all_items, ensure_ascii=False)}
            """
            res_text, success = call_gemini(prompt)
            
            msg = MIMEMultipart()
            msg['Subject'] = f"📅 [분석완료] {target} 글로벌 뉴스 리포트"
            msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
            body = res_text + "\n\n🔗 [참조 링크]\n" + "\n".join([f"- {n['title']}: {n['link']}" for n in all_items])
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
                server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
