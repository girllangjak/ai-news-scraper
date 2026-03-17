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

# [환경 설정] 모델 우선순위 최신화
MODEL_PRIORITY = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

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

def fetch_reddit_trends(topic):
    """레딧 주요 주식 게시판에서 키워드 관련 최신 여론 수집"""
    print(f"🔥 레딧 여론 조사 중: {topic}")
    subreddits = ["wallstreetbets", "stocks", "investing"]
    reddit_results = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for sub in subreddits:
        # 최근 3일 이내, 관련도 높은 순 검색
        url = f"https://www.reddit.com/r/{sub}/search.json?q={quote(topic)}&restrict_sr=1&sort=new&limit=5"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                posts = res.json().get('data', {}).get('children', [])
                for p in posts:
                    d = p['data']
                    reddit_results.append({
                        "source": f"Reddit/r/{sub}",
                        "title": d['title'],
                        "ups": d['ups'],
                        "link": f"https://www.reddit.com{d['permalink']}"
                    })
        except: continue
    return reddit_results[:10] # 최대 10개 반환

def fetch_news_data(topic, countries):
    limit_3d = datetime.now(timezone.utc) - timedelta(days=3)
    results = {"domestic": [], "international": [], "reddit": []}
    
    # 1. 국내 뉴스 (네이버) - 10개 확보
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=50&sort=date"
        headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
        items = requests.get(n_url, headers=headers).json().get('items', [])
        for it in items:
            title = re.sub('<.*?>', '', it['title'])
            results["domestic"].append({"title": title, "link": it['link']})
            if len(results["domestic"]) >= 10: break
    except: pass

    # 2. 해외 뉴스 (구글 RSS) - 10개 확보
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
                if len(results["international"]) >= 10: break
            if len(results["international"]) >= 10: break
        except: continue

    # 3. 레딧 여론 수집
    results["reddit"] = fetch_reddit_trends(topic)
            
    return results

def analyze_topic(topic):
    countries = get_target_countries_and_queries(topic)
    data = fetch_news_data(topic, countries)
    
    if not data["domestic"] and not data["international"] and not data["reddit"]:
        return f"### 📌 주제: {topic}\n- 수집된 데이터가 전혀 없습니다.\n", []

    prompt = f"""
    주제: {topic}
    뉴스 데이터: {json.dumps(data['domestic'] + data['international'], ensure_ascii=False)}
    레딧 여론: {json.dumps(data['reddit'], ensure_ascii=False)}
    
    지침:
    1. 반드시 한국어로 작성.
    2. [국내외 시각 차이]: 공식 보도들의 온도 차이를 분석하라.
    3. [레딧 민심 분석]: 뉴스 보도와 현지 개미(Reddit)들의 반응이 어떻게 다른지 집중 분석하라. (추천 수 등을 참고하여 탐욕/공포 파악)
    4. [결론]: 투자 관점에서 주목해야 할 핵심 3줄 요약.
    5. 기사가 3일 이상 지난 과거 기사라면 '과거 기록 기반 분석'임을 명시하라.
    """
    report, success = call_gemini(prompt)
    links = data["domestic"] + data["international"] + data["reddit"]
    return report if success else f"### 📌 주제: {topic}\n- AI 분석 실패\n", links

if __name__ == "__main__":
    print("🚀 글로벌 이슈 분석 및 레딧 여론 수집 봇 가동")
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

        msg = MIMEMultipart()
        msg['Subject'] = f"🌐 [인텔리전스] 이슈 {len(issues)}건 통합 리포트 (레딧 여론 포함)"
        msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
        
        ref_text = "\n\n🔗 [참조 링크 모음]\n"
        for issue in issues:
            topic = issue['title']
            ref_text += f"\n[{topic} 관련 참조 리스트]\n"
            for l in all_refs:
                # 링크 소스 구분 표시 (레딧인지 뉴스인지)
                src = l.get('country') or l.get('source') or '국내'
                ref_text += f"- [{src}] {l['title']}: {l['link']}\n"
        
        msg.attach(MIMEText(full_body + ref_text, 'plain'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
            server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
        print(f"✅ {len(issues)}건 분석 완료 및 메일 발송.")
