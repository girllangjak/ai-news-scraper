import requests
import smtplib
import os
import xml.etree.ElementTree as ET
import json
import re
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

# [모델 설정]
MODEL_PRIORITY = ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]

CONFIG = {
    "NAVER": {"ID": os.environ.get("NAVER_ID"), "SEC": os.environ.get("NAVER_SECRET")},
    "MAIL": {"USER": os.environ.get("GMAIL_USER"), "PW": os.environ.get("GMAIL_PW")},
    "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "REPO": "girllangjak/ai-news-scraper"
}

def call_gemini(prompt, is_json=False):
    """AI 호출 로그를 남기는 Gemini 함수"""
    start_time = time.time()
    for model in MODEL_PRIORITY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={CONFIG['GEMINI_KEY']}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json" if is_json else "text/plain",
                "temperature": 0.1
            }
        }
        try:
            res = requests.post(url, json=payload, timeout=60)
            elapsed = round(time.time() - start_time, 2)
            if res.status_code == 200:
                text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                return text, f"성공({model}, {elapsed}초)"
        except Exception as e:
            continue
    return None, f"실패(모든 모델 응답 없음, {round(time.time() - start_time, 2)}초)"

def fetch_all_data_with_logs(topic):
    """각 수집 단계별 로그(각주)를 생성하며 데이터 수집"""
    logs = []
    limit_3d = datetime.now(timezone.utc) - timedelta(days=3)
    results = {"domestic": [], "international": [], "reddit": []}

    # 1. 국가/쿼리 생성 로그
    q_prompt = f"주제 '{topic}' 분석용 국가 3곳/현지어 검색어 JSON 생성."
    q_res, q_log = call_gemini(q_prompt, is_json=True)
    countries = json.loads(q_res).get("countries", []) if q_res else []
    logs.append(f"📍 쿼리 생성: {q_log}")

    # 2. 국내 뉴스 수집 로그
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=30&sort=date"
        headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
        n_res = requests.get(n_url, headers=headers).json().get('items', [])
        for it in n_res:
            title = re.sub('<.*?>', '', it['title'])
            results["domestic"].append({"title": title, "link": it['link']})
            if len(results["domestic"]) >= 10: break
        logs.append(f"📍 네이버 뉴스: {len(results['domestic'])}건 확보")
    except:
        logs.append("📍 네이버 뉴스: 수집 오류")

    # 3. 해외 뉴스 수집 로그
    intl_count = 0
    for c in countries:
        g_url = f"https://news.google.com/rss/search?q={quote(c['query'])}&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
        try:
            root = ET.fromstring(requests.get(g_url, timeout=10).text)
            for it in root.findall('.//item')[:4]:
                results["international"].append({"country": c['name'], "title": it.find('title').text, "link": it.find('link').text})
                intl_count += 1
            if intl_count >= 10: break
        except: continue
    logs.append(f"📍 구글 외신: {intl_count}건 확보")

    # 4. 레딧 여론 수집 로그
    reddit_count = 0
    headers = {"User-Agent": "Mozilla/5.0"}
    for sub in ["wallstreetbets", "stocks"]:
        try:
            r_url = f"https://www.reddit.com/r/{sub}/search.json?q={quote(topic)}&restrict_sr=1&sort=new&limit=5"
            r_res = requests.get(r_url, headers=headers, timeout=10).json().get('data', {}).get('children', [])
            for p in r_res:
                results["reddit"].append({"source": sub, "title": p['data']['title'], "ups": p['data']['ups']})
                reddit_count += 1
        except: continue
    logs.append(f"📍 레딧 여론: {reddit_count}건 확보")

    return results, logs

def analyze_topic(topic):
    data, logs = fetch_all_data_with_logs(topic)
    
    # 데이터 요약 (AI 부하 감소)
    d_titles = [n['title'] for n in data['domestic'][:5]]
    i_titles = [f"[{n['country']}] {n['title']}" for n in data['international'][:5]]
    r_titles = [f"({r['source']}) {r['title']}" for r in data['reddit'][:5]]

    prompt = f"주제: {topic}\n뉴스:\n{d_titles}\n{i_titles}\n레딧:\n{r_titles}\n\n위 데이터를 바탕으로 시장의 온도차와 투자 리스크를 한국어 3줄로 요약해."
    
    report, ai_log = call_gemini(prompt)
    logs.append(f"📍 AI 분석: {ai_log}")

    if not report or "오류" in ai_log:
        report = f"### [분석 지연] {topic}\n현재 수집된 데이터량이 분석 모델의 처리 한계를 초과했거나 API 응답이 지연되고 있습니다."

    return report, data, logs

if __name__ == "__main__":
    issue_url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    issues = requests.get(issue_url, headers={"Authorization": f"token {CONFIG['GH_TOKEN']}"}).json()
    
    if issues and isinstance(issues, list):
        full_body = ""
        all_refs = ""
        
        for issue in issues:
            topic = issue['title']
            report, data, logs = analyze_topic(topic)
            
            # 본문에 리포트와 각주(Log) 추가
            full_body += f"## 📅 주제: {topic}\n{report}\n\n"
            full_body += "**[시스템 작업 로그]**\n" + "\n".join(logs) + "\n\n---\n"
            
            # 참조 링크 정리
            all_refs += f"\n### 🔗 {topic} 참조 링크\n"
            for l in data['domestic'] + data['international']:
                all_refs += f"- {l['title']} ({l['link']})\n"

        msg = MIMEMultipart()
        msg['Subject'] = f"🌐 [인텔리전스] 이슈 {len(issues)}건 통합 리포트"
        msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
        msg.attach(MIMEText(full_body + all_refs, 'plain'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
            server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
        print("✅ 리포트 및 로그 발송 완료")
