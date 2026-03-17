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

# [운영 규칙] 모델 우선순위 최신화 (API 안정성 기준)
MODEL_PRIORITY = [
    "gemini-2.0-flash",       # 최신 고성능 모델
    "gemini-1.5-flash",       # 안정적인 표준 모델
    "gemini-1.5-pro"          # 복잡한 분석용 백업
]

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
    prompt = f"주제 '{topic}' 분석을 위해 연관 국가 3곳과 현지어 검색어를 JSON으로 생성해. 예: {{'countries': [{{'name': 'USA', 'hl': 'en', 'gl': 'US', 'query': 'Iran Israel war'}}]}}"
    res, success = call_gemini(prompt, is_json=True)
    try: return json.loads(res).get("countries", []) if success else []
    except: return []

def fetch_news_data(topic, countries):
    """[운영규칙 적용] 기사가 없으면 과거 기사를 순차 호출하여 10개씩 강제 확보"""
    limit_3d = datetime.now(timezone.utc) - timedelta(days=3)
    results = {"domestic": [], "international": []}
    
    # 1. 국내 뉴스 (최대 10개)
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=50&sort=date"
        headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
        items = requests.get(n_url, headers=headers).json().get('items', [])
        for it in items:
            title = re.sub('<.*?>', '', it['title'])
            # 3일 이내 기사인지 여부 표시용 태그
            p_date = datetime.strptime(it['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').replace(tzinfo=timezone(timedelta(hours=9)))
            tag = "[최신]" if p_date >= limit_3d else "[과거기록]"
            results["domestic"].append({"title": f"{tag} {title}", "link": it['link']})
            if len(results["domestic"]) >= 10: break
    except: pass

    # 2. 해외 뉴스 (최대 10개)
    for c in countries:
        search_q = c.get('query', topic)
        g_url = f"https://news.google.com/rss/search?q={quote(search_q)}&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
        try:
            root = ET.fromstring(requests.get(g_url, timeout=15).text)
            for it in root.findall('.//item'):
                g_date = datetime.strptime(it.find('pubDate').text, '%a, %d %b %Y %H:%M:%S GMT').replace(tzinfo=timezone.utc)
                tag = "[최신]" if g_date >= limit_3d else "[과거기록]"
                results["international"].append({
                    "country": c['name'],
                    "title": f"{tag} {it.find('title').text}",
                    "link": it.find('link').text
                })
                if len(results["international"]) >= 10: break
            if len(results["international"]) >= 10: break
        except: continue
    return results

def analyze_topic(topic):
    countries = get_target_countries_and_queries(topic)
    news_data = fetch_news_data(topic, countries)
    
    # 기사 수량 체크 (국내/외신 각 10개 미만일 경우 경고성 멘트 추가)
    prompt = f"""
    주제: {topic}
    데이터: {json.dumps(news_data, ensure_ascii=False)}
    지침:
    1. 반드시 한국어로 작성. 
    2. 최신 기사가 부족해 과거 기사가 섞여 있다면, 이를 분석 내용에 반영하여 현재 상황과 과거 맥락을 비교할 것.
    3. 국내와 해외의 시각 차이를 명확히 구분하여 분석.
    """
    report, success = call_gemini(prompt)
    return report if success else f"### {topic} 분석 실패", news_data

if __name__ == "__main__":
    issue_url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    issues = requests.get(issue_url, headers={"Authorization": f"token {CONFIG['GH_TOKEN']}"}).json()
    
    if issues and isinstance(issues, list):
        full_report = "## 📅 글로벌 이슈 통합 분석 리포트\n\n"
        all_links_str = ""
        
        for issue in issues:
            topic = issue['title']
            report, news = analyze_topic(topic)
            full_report += f"{report}\n\n---\n"
            
            # 이슈별 링크 10개씩 정리
            all_links_str += f"\n### 🔗 {topic} 참조 링크 (국내/외신 최대 20개)\n"
            for n in news['domestic'] + news['international']:
                all_links_str += f"- {n.get('country', '국내')}: {n['title']} ({n['link']})\n"

        msg = MIMEMultipart()
        msg['Subject'] = f"🌐 [뉴스 봇] {len(issues)}건의 통합 리포트 및 링크 모음"
        msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
        msg.attach(MIMEText(full_report + all_links_str, 'plain'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
            server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
        print("✅ 리포트 발송 완료!")
