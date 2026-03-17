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

# [운영 설정] 2026년 최신 API 모델 우선순위
MODEL_PRIORITY = ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]

CONFIG = {
    "NAVER": {"ID": os.environ.get("NAVER_ID"), "SEC": os.environ.get("NAVER_SECRET")},
    "MAIL": {"USER": os.environ.get("GMAIL_USER"), "PW": os.environ.get("GMAIL_PW")},
    "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "REPO": "girllangjak/ai-news-scraper"
}

def call_gemini(prompt, is_json=False):
    """Gemini API 호출 (타임아웃 연장 및 실패 복구 로직)"""
    for model in MODEL_PRIORITY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={CONFIG['GEMINI_KEY']}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json" if is_json else "text/plain",
                "temperature": 0.1 if is_json else 0.3
            }
        }
        try:
            res = requests.post(url, json=payload, timeout=60)
            if res.status_code == 200:
                text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                if text: return text, True
        except: continue
    return "AI 분석 엔진 일시 오류", False

def get_target_countries(topic):
    """AI를 통한 국가 및 현지어 쿼리 생성"""
    prompt = f"주제 '{topic}' 분석을 위해 연관 국가 3곳과 현지어 검색어를 JSON으로 생성해. 예: {{'countries': [{{'name': 'USA', 'hl': 'en', 'gl': 'US', 'query': 'Iran Israel war'}}]}}"
    res, success = call_gemini(prompt, is_json=True)
    try: return json.loads(res).get("countries", []) if success else []
    except: return []

def fetch_reddit_trends(topic):
    """레딧(r/wallstreetbets 등) 실시간 여론 수집"""
    subreddits = ["wallstreetbets", "stocks", "investing"]
    reddit_results = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for sub in subreddits:
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
    return reddit_results[:10]

def fetch_all_data(topic):
    """국내 10개, 국외 10개, 레딧 10개 강제 수집 로직"""
    limit_3d = datetime.now(timezone.utc) - timedelta(days=3)
    results = {"domestic": [], "international": [], "reddit": []}
    countries = get_target_countries(topic)
    
    # 1. 국내 뉴스 (네이버) - 10개 확보
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=50&sort=date"
        headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
        items = requests.get(n_url, headers=headers).json().get('items', [])
        for it in items:
            title = re.sub('<.*?>', '', it['title'])
            p_date = datetime.strptime(it['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').replace(tzinfo=timezone(timedelta(hours=9)))
            tag = "[최신]" if p_date >= limit_3d else "[과거]"
            results["domestic"].append({"title": f"{tag} {title}", "link": it['link']})
            if len(results["domestic"]) >= 10: break
    except: pass

    # 2. 해외 뉴스 (구글 RSS) - 10개 확보
    for c in countries:
        search_q = c.get('query', topic)
        g_url = f"https://news.google.com/rss/search?q={quote(search_q)}&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
        try:
            root = ET.fromstring(requests.get(g_url, timeout=15).text)
            for it in root.findall('.//item'):
                g_date = datetime.strptime(it.find('pubDate').text, '%a, %d %b %Y %H:%M:%S GMT').replace(tzinfo=timezone.utc)
                tag = "[최신]" if g_date >= limit_3d else "[과거]"
                results["international"].append({
                    "country": c['name'], "title": f"{tag} {it.find('title').text}", "link": it.find('link').text
                })
                if len(results["international"]) >= 10: break
            if len(results["international"]) >= 10: break
        except: continue

    # 3. 레딧 여론 수집
    results["reddit"] = fetch_reddit_trends(topic)
    return results

def analyze_topic(topic):
    data = fetch_all_data(topic)
    
    # AI 과부하 방지를 위한 텍스트 정제 및 요약 전달 (핵심 5~7개씩만)
    d_summary = "\n".join([f"- {n['title']}" for n in data['domestic'][:7]])
    i_summary = "\n".join([f"- [{n['country']}] {n['title']}" for n in data['international'][:7]])
    r_summary = "\n".join([f"- [{r['source']}] {r['title']} (추천:{r['ups']})" for r in data['reddit'][:5]])

    prompt = f"""
    주제: {topic}
    ---
    [뉴스 데이터]
    {d_summary}
    {i_summary}
    
    [레딧 여론]
    {r_summary}
    ---
    명령:
    1. 뉴스 보도와 레딧 여론의 결정적 차이점을 한 줄로 요약하라.
    2. 현재 시장의 '공포/탐욕' 여부를 레딧 반응 기반으로 판단하라.
    3. 투자자가 오늘 주목해야 할 리스크/기회를 3줄 요약하라.
    4. 분석 내용에 과거 기사가 포함된 경우 반드시 명시하라.
    """
    
    report, success = call_gemini(prompt)
    if not success:
        report = f"### [분석 지연] {topic}\n데이터 과부하로 요약에 실패했습니다. 하단 링크를 직접 확인 바랍니다."
    
    all_links = data['domestic'] + data['international'] + data["reddit"]
    return report, all_links

if __name__ == "__main__":
    issue_url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    issues = requests.get(issue_url, headers={"Authorization": f"token {CONFIG['GH_TOKEN']}"}).json()
    
    if issues and isinstance(issues, list):
        full_report = f"## 📅 {datetime.now().strftime('%Y-%m-%d')} 통합 리포트 (레딧 포함)\n\n"
        all_refs = ""
        
        for issue in issues:
            topic = issue['title']
            print(f"🔎 분석 중: {topic}")
            report, links = analyze_topic(topic)
            full_report += f"{report}\n\n---\n"
            
            all_refs += f"\n[{topic} 참조 링크]\n"
            for l in links:
                src = l.get('country') or l.get('source') or '국내'
                all_refs += f"- [{src}] {l['title']} ({l['link']})\n"

        msg = MIMEMultipart()
        msg['Subject'] = f"🌐 [인텔리전스] 오늘자 이슈 {len(issues)}건 통합 리포트"
        msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
        msg.attach(MIMEText(full_report + all_refs, 'plain'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
            server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
        print("✅ 리포트 발송 완료!")
