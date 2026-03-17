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

# 최신 모델 설정
MODEL_PRIORITY = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-1.5-flash-latest"]

CONFIG = {
    "NAVER": {"ID": os.environ.get("NAVER_ID"), "SEC": os.environ.get("NAVER_SECRET")},
    "MAIL": {"USER": os.environ.get("GMAIL_USER"), "PW": os.environ.get("GMAIL_PW")},
    "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "REPO": "girllangjak/ai-news-scraper"
}

def call_gemini(prompt, is_json=False):
    """Gemini API 호출 (언어 및 출력 형식 제어)"""
    for model in MODEL_PRIORITY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={CONFIG['GEMINI_KEY']}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"} if is_json else {}
        }
        try:
            res = requests.post(url, json=payload, timeout=40)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip(), True
        except: continue
    return "", False

def get_target_countries(topic):
    """AI가 키워드를 보고 연관 국가와 언어 코드를 추천"""
    prompt = f"""
    키워드 '{topic}'와(과) 가장 밀접한 관련이 있는 국가 3곳을 선정하고 해당 국가의 언어코드(hl)와 지역코드(gl)를 JSON 형식으로 반환해줘.
    예: {{"countries": [{{"name": "Israel", "hl": "iw", "gl": "IL"}}, {{"name": "Iran", "hl": "fa", "gl": "IR"}}]}}
    반드시 이 JSON 형식만 출력해.
    """
    res, success = call_gemini(prompt, is_json=True)
    try:
        return json.loads(res).get("countries", []) if success else []
    except: return []

def fetch_global_news(topic, countries):
    """국가별 현지 언어로 뉴스 수집"""
    global_news = []
    for c in countries:
        print(f"🌍 {c['name']} 현지 뉴스 수집 중... ({c['hl']}-{c['gl']})")
        # 구글 뉴스 RSS (3일 이내 제한)
        g_url = f"https://news.google.com/rss/search?q={quote(topic)}+when:3d&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
        try:
            res = requests.get(g_url, timeout=20)
            root = ET.fromstring(res.text)
            for it in root.findall('.//item')[:3]: # 국가당 상위 3개
                global_news.append({
                    "country": c['name'],
                    "title": it.find('title').text,
                    "link": it.find('link').text
                })
        except: continue
    return global_news

def fetch_naver_news(topic):
    """국내 뉴스 수집"""
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=5&sort=date"
    headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
    try:
        items = requests.get(url, headers=headers).json().get('items', [])
        return [{"src": "국내", "title": re.sub('<.*?>', '', it['title']), "link": it['link']} for it in items]
    except: return []

if __name__ == "__main__":
    # 1. 키워드 획득 (GitHub Issue)
    issue_url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    issues = requests.get(issue_url, headers={"Authorization": f"token {CONFIG['GH_TOKEN']}"}).json()
    
    if issues and isinstance(issues, list):
        topic = issues[0]['title']
        print(f"🚀 분석 시작: {topic}")

        # 2. 연관 국가 선정 및 뉴스 수집
        target_countries = get_target_countries(topic)
        kr_news = fetch_naver_news(topic)
        intl_news = fetch_global_news(topic, target_countries)
        
        all_data = {"domestic": kr_news, "international": intl_news}

        # 3. AI 심층 분석 (번역 및 요약)
        analysis_prompt = f"""
        주제: {topic}
        다음은 한국 및 관련 국가들({[c['name'] for c in target_countries]})의 현지 뉴스 데이터야.
        
        지침:
        1. 각 국가별(현지 시각) 뉴스를 한국어로 번역하고 핵심 내용을 요약해줘.
        2. 국내 보도와 현지 보도의 온도 차이나 시각 차이를 비교 분석해줘.
        3. 마지막에 전체적인 상황을 3줄로 결론지어줘.
        
        데이터: {json.dumps(all_data, ensure_ascii=False)}
        """
        report, success = call_gemini(analysis_prompt)

        if success:
            # 4. 이메일 발송
            msg = MIMEMultipart()
            msg['Subject'] = f"🌐 [글로벌 리포트] {topic}"
            msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
            msg.attach(MIMEText(report + "\n\n--- 수집 링크 ---\n" + "\n".join([f"- {n['title']}: {n['link']}" for n in kr_news + intl_news]), 'plain'))
            
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
                server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
            print("✅ 분석 리포트 발송 완료!")
