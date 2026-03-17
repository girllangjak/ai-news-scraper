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

# ==========================================
# [설정 섹션] 관리자님의 정보를 입력해주세요
# ==========================================
# 1. 확인된 2026년 최신 모델 우선순위
MODEL_PRIORITY = [
    "gemini-3.1-flash-lite-preview", # 최우선 (2026-03)
    "gemini-3.1-pro-preview",        # 차선 (2026-01)
    "gemini-2.5-flash"               # 백업
]

# 2. 필수 인증 정보
CREDENTIALS = {
    "GEMINI_KEY": "여기에_GEMINI_API_키를_넣으세요",
    "NAVER_ID": "여기에_네이버_클라이언트_ID",
    "NAVER_SEC": "여기에_네이버_클라이언트_시크릿",
    "GMAIL_USER": "관리자_이메일@gmail.com",
    "GMAIL_PW": "구글_앱_비밀번호", # 일반 비번이 아닌 '앱 비밀번호' 16자리
    "GH_TOKEN": "선택사항_깃허브_토큰",
    "REPO": "girllangjak/ai-news-scraper"
}
# ==========================================

def call_gemini(prompt, is_json=False):
    """최신 모델 ID를 사용하여 Gemini API 호출"""
    start_time = time.time()
    for model in MODEL_PRIORITY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={CREDENTIALS['GEMINI_KEY']}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json" if is_json else "text/plain",
                "temperature": 0.2
            }
        }
        try:
            res = requests.post(url, json=payload, timeout=30)
            elapsed = round(time.time() - start_time, 2)
            if res.status_code == 200:
                text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                return text, f"성공({model}, {elapsed}s)"
        except: continue
    return None, f"실패(인증/모델확인필요, {round(time.time() - start_time, 2)}s)"

def fetch_data(topic):
    """네이버, 구글외신, 레딧 데이터 수집 및 로그 생성"""
    logs = []
    results = {"domestic": [], "international": [], "reddit": []}

    # 1. 쿼리 생성
    q_prompt = f"Topic: {topic}. Generate 3 countries and local search queries in JSON: {{'countries': [{{'name': 'USA', 'hl': 'en', 'gl': 'US', 'query': '...'}}]}}"
    q_res, q_log = call_gemini(q_prompt, is_json=True)
    logs.append(f"📍 쿼리 생성: {q_log}")
    
    countries = [{"name": "USA", "hl": "en", "gl": "US", "query": topic}]
    if q_res:
        try: countries = json.loads(q_res).get("countries", countries)
        except: pass

    # 2. 네이버 뉴스 (10개)
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=20&sort=date"
        headers = {"X-Naver-Client-Id": CREDENTIALS['NAVER_ID'], "X-Naver-Client-Secret": CREDENTIALS['NAVER_SEC']}
        n_items = requests.get(n_url, headers=headers).json().get('items', [])
        for it in n_items:
            results["domestic"].append({"title": re.sub('<.*?>', '', it['title']), "link": it['link']})
            if len(results["domestic"]) >= 10: break
        logs.append(f"📍 네이버 뉴스: {len(results['domestic'])}건")
    except: logs.append("📍 네이버 뉴스: 오류")

    # 3. 구글 외신 (10개)
    for c in countries:
        try:
            g_url = f"https://news.google.com/rss/search?q={quote(c['query'])}&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
            root = ET.fromstring(requests.get(g_url, timeout=10).text)
            for it in root.findall('.//item')[:4]:
                results["international"].append({"country": c['name'], "title": it.find('title').text, "link": it.find('link').text})
            if len(results["international"]) >= 10: break
        except: continue
    logs.append(f"📍 구글 외신: {len(results['international'])}건")

    # 4. 레딧 여론 (10개)
    headers = {"User-Agent": "Mozilla/5.0"}
    for sub in ["wallstreetbets", "stocks", "investing"]:
        try:
            r_url = f"https://www.reddit.com/r/{sub}/search.json?q={quote(topic)}&restrict_sr=1&sort=new&limit=5"
            r_res = requests.get(r_url, headers=headers, timeout=10).json().get('data', {}).get('children', [])
            for p in r_res:
                results["reddit"].append({"source": sub, "title": p['data']['title'], "ups": p['data']['ups']})
            if len(results["reddit"]) >= 10: break
        except: continue
    logs.append(f"📍 레딧 여론: {len(results['reddit'])}건")

    return results, logs

def analyze(topic):
    """수집된 데이터를 요약하여 최종 리포트 생성"""
    data, logs = fetch_data(topic)
    
    # AI 부하 방지를 위한 압축 (최신 5개씩만)
    prompt = f"""
    주제: {topic}
    뉴스: {[n['title'] for n in data['domestic'][:5]]}
    외신: {[f"[{n['country']}] {n['title']}" for n in data['international'][:5]]}
    레딧: {[f"({r['source']}) {r['title']}" for r in data['reddit'][:5]]}
    
    위 데이터를 기반으로 시장의 핵심 흐름과 투자 시각의 차이를 한국어로 3줄 요약하라.
    """
    report, ai_log = call_gemini(prompt)
    logs.append(f"📍 최종 분석: {ai_log}")

    if not report:
        report = "### [분석 지연] 데이터는 수집되었으나 AI가 응답하지 않습니다. 로그를 확인해 주세요."

    return report, data, logs

if __name__ == "__main__":
    # 1. 이슈 목록 가져오기 (GitHub 연동 실패 시 테스트 키워드 사용)
    try:
        issue_url = f"https://api.github.com/repos/{CREDENTIALS['REPO']}/issues?state=open"
        issues = requests.get(issue_url, headers={"Authorization": f"token {CREDENTIALS['GH_TOKEN']}"}).json()
        if not isinstance(issues, list): issues = [{"title": "미국 증시 테크주 수급 분석"}]
    except:
        issues = [{"title": "미국 증시 테크주 수급 분석"}]

    full_body = f"## 📅 {datetime.now().strftime('%Y-%m-%d')} 통합 리포트\n\n"
    all_refs = ""

    for issue in issues:
        topic = issue['title']
        print(f"🔎 {topic} 분석 중...")
        report, data, logs = analyze(topic)
        
        full_body += f"### 📌 주제: {topic}\n{report}\n\n**[시스템 로그]**\n" + "\n".join(logs) + "\n\n---\n"
        
        all_refs += f"\n### 🔗 {topic} 참조 링크\n"
        for l in data['domestic'] + data['international']:
            all_refs += f"- {l['title']} ({l['link']})\n"

    # 2. 이메일 발송
    msg = MIMEMultipart()
    msg['Subject'] = f"🌐 [인텔리전스] {len(issues)}건 분석 보고서"
    msg['From'] = msg['To'] = CREDENTIALS['GMAIL_USER']
    msg.attach(MIMEText(full_body + all_refs, 'plain'))
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CREDENTIALS['GMAIL_USER'], CREDENTIALS['GMAIL_PW'])
            server.sendmail(CREDENTIALS['GMAIL_USER'], CREDENTIALS['GMAIL_USER'], msg.as_string())
        print("✅ 보고서 발송 완료!")
    except Exception as e:
        print(f"⚠️ 발송 오류: {e}\n\n[보고서 내용]\n{full_body}")
