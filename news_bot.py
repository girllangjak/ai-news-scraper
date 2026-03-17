import requests
import smtplib
import os
import xml.etree.ElementTree as ET
import json
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

# [환경 설정] 모델 우선순위
MODEL_PRIORITY = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-1.5-flash-latest"]

CONFIG = {
    "NAVER": {"ID": os.environ.get("NAVER_ID"), "SEC": os.environ.get("NAVER_SECRET")},
    "MAIL": {"USER": os.environ.get("GMAIL_USER"), "PW": os.environ.get("GMAIL_PW")},
    "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "REPO": "girllangjak/ai-news-scraper"
}

def call_gemini(prompt, is_json=False):
    for model in MODEL_PRIORITY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={CONFIG['GEMINI_KEY']}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"} if is_json else {"temperature": 0.2}
        }
        try:
            res = requests.post(url, json=payload, timeout=45)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip(), True
        except: continue
    return "", False

def get_target_countries_and_queries(topic):
    prompt = f"""
    주제 '{topic}'에 대해 국제 뉴스를 수집하려 함. 
    연관 국가 3곳과 해당 국가 언어로 된 '현지어 검색어'를 포함해 JSON으로 응답해.
    반드시 영어권(US)과 핵심 관련국을 포함할 것.
    형식: {{ "countries": [{{ "name": "국가명", "hl": "언어코드", "gl": "지역코드", "query": "현지어검색어" }}] }}
    """
    res, success = call_gemini(prompt, is_json=True)
    try: return json.loads(res).get("countries", []) if success else []
    except: return []

def fetch_news_data(topic, countries):
    """3일 이내 우선 수집, 부족 시 과거 데이터로 10개 충원"""
    limit_3d = datetime.now(timezone.utc) - timedelta(days=3)
    results = {"domestic": [], "international": []}
    
    # 1. 국내 뉴스 (네이버) - 최대 10개 확보 시도
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=50&sort=date"
        headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
        items = requests.get(n_url, headers=headers).json().get('items', [])
        
        # 날짜순으로 정렬되어 있으므로 순차적으로 담음 (최신 우선)
        for it in items:
            title = re.sub('<.*?>', '', it['title'])
            results["domestic"].append({"title": title, "link": it['link']})
            if len(results["domestic"]) >= 10: break
    except: pass

    # 2. 해외 뉴스 (국가별 구글 RSS) - 국가당 3~4개씩 총 10개 확보 시도
    for c in countries:
        search_q = c.get('query', topic)
        g_url = f"https://news.google.com/rss/search?q={quote(search_q)}&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
        try:
            root = ET.fromstring(requests.get(g_url, timeout=15).text)
            for it in root.findall('.//item'):
                results["international"].append({
                    "country": c['name'],
                    "title": it.find('title').text,
                    "link": it.find('link').text
                })
                # 전체 10개 차면 중단 (국가별 균형보다 수량 우선)
                if len(results["international"]) >= 10: break
            if len(results["international"]) >= 10: break
        except: continue
            
    return results

def analyze_topic(topic):
    countries = get_target_countries_and_queries(topic)
    news_data = fetch_news_data(topic, countries)
    
    if not news_data["domestic"] and not news_data["international"]:
        return f"### 📌 주제: {topic}\n- 검색된 기사가 전혀 없습니다.\n", []

    # AI 분석 프롬프트 (최신성 강조 및 요약 지침)
    prompt = f"""
    주제: {topic}
    기사 데이터: {json.dumps(news_data, ensure_ascii=False)}
    
    지침:
    1. 반드시 한국어로 작성.
    2. [현지 시각 분석]: 수집된 기사를 바탕으로 각국의 시각을 요약. 
    3. [국내외 시각 차이]: 보도 경향 분석. 
    4. 만약 기사 발행일이 3일을 초과한 과거 기사라면 '과거 기록 기반 분석'임을 명시할 것.
    """
    report, success = call_gemini(prompt)
    links = news_data["domestic"] + news_data["international"]
    return report if success else f"### 📌 주제: {topic}\n- AI 분석 실패\n", links

if __name__ == "__main__":
    issue_url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    issues = requests.get(issue_url, headers={"Authorization": f"token {CONFIG['GH_TOKEN']}"}).json()
    
    if issues and isinstance(issues, list):
        full_body = f"## 📅 {datetime.now().strftime('%Y-%m-%d')} 글로벌 통합 리포트\n\n"
        all_refs = []
        
        for issue in issues:
            topic = issue['title']
            report, links = analyze_topic(topic)
            full_body += f"{report}\n\n---\n"
            all_refs.extend(links)

        # 메일 발송
        msg = MIMEMultipart()
        msg['Subject'] = f"🌐 [분석보고] 등록된 이슈 {len(issues)}건에 대한 통합 리포트"
        msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
        
        # 참조 링크 10개씩 구분하여 정리
        ref_text = "\n\n🔗 [참조 링크 모음]\n"
        for issue in issues:
            topic = issue['title']
            ref_text += f"\n[{topic} 관련 기사]\n"
            # 해당 이슈에 대한 링크만 필터링하거나 전체 나열
            for l in all_refs:
                ref_text += f"- {l['title']}: {l['link']}\n"
        
        msg.attach(MIMEText(full_body + ref_text, 'plain'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
            server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
        print(f"✅ {len(issues)}건 분석 완료 및 메일 발송.")
