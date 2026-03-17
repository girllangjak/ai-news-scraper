import requests, smtplib, os, json, re, time
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# [관리자님 계정 전용 2026년형 모델 리스트]
MODEL_PRIORITY = ["gemini-3.1-flash-lite-preview", "gemini-3.1-pro-preview", "gemini-2.5-flash"]

def get_env(key):
    return os.environ.get(key, "")

def call_gemini(prompt, is_json=False):
    key = get_env("GEMINI_API_KEY")
    if not key: return None, "No API Key"
    for model in MODEL_PRIORITY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json" if is_json else "text/plain", "temperature": 0.2}
        }
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip(), model
        except: continue
    return None, "All Models Failed"

def fetch_all_data(topic):
    """국내 뉴스 + 구글 외신 + 레딧 여론 수집"""
    results = {"domestic": [], "international": [], "reddit": []}
    
    # 1. 쿼리 생성
    q_prompt = f"Topic: {topic}. Generate 2 focus countries and local queries in JSON."
    q_res, _ = call_gemini(q_prompt, is_json=True)
    countries = [{"name": "USA", "hl": "en", "gl": "US", "query": topic}]
    if q_res:
        try:
            start_idx = q_res.find('{')
            end_idx = q_res.rfind('}') + 1
            countries = json.loads(q_res[start_idx:end_idx]).get("countries", countries)
        except: pass

    # 2. 네이버 뉴스
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=5"
        headers = {"X-Naver-Client-Id": get_env("NAVER_ID"), "X-Naver-Client-Secret": get_env("NAVER_SECRET")}
        n_res = requests.get(n_url, headers=headers).json().get('items', [])
        results["domestic"] = [re.sub('<.*?>', '', i['title']) for i in n_res]
    except: pass

    # 3. 구글 외신
    for c in countries:
        try:
            g_url = f"https://news.google.com/rss/search?q={quote(c['query'])}&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
            res = requests.get(g_url, timeout=10)
            titles = re.findall(r'<title>(.*?)</title>', res.text)[1:4]
            results["international"].extend([f"[{c['name']}] {t}" for t in titles])
        except: continue

    # 4. 레딧 여론
    headers = {"User-Agent": "Mozilla/5.0"}
    for sub in ["wallstreetbets", "stocks"]:
        try:
            r_url = f"https://www.reddit.com/r/{sub}/search.json?q={quote(topic)}&restrict_sr=1&limit=3"
            r_res = requests.get(r_url, headers=headers, timeout=10).json()
            posts = [p['data']['title'] for p in r_res.get('data', {}).get('children', [])]
            results["reddit"].extend([f"({sub}) {p}" for p in posts])
        except: continue
    return results

def main_process():
    """이 함수가 실제로 모든 것을 실행하고 메일을 보냅니다"""
    repo = get_env("GITHUB_REPOSITORY")
    token = get_env("GH_TOKEN")
    
    # 키워드 가져오기
    issues = [{"title": "글로벌 경제 및 반도체 시장 동향"}]
    if repo and token:
        try:
            issue_url = f"https://api.github.com/repos/{repo}/issues?state=open"
            res = requests.get(issue_url, headers={"Authorization": f"token {token}"}).json()
            if isinstance(res, list) and len(res) > 0: issues = res
        except: pass

    full_report = f"## 📅 {datetime.now().strftime('%Y-%m-%d')} 인텔리전스 리포트\n\n"

    for issue in issues:
        topic = issue['title']
        print(f"🔎 분석 중: {topic}")
        data = fetch_all_data(topic)
        
        prompt = f"주제: {topic}\n뉴스: {data['domestic']}\n외신: {data['international']}\n레딧: {data['reddit']}\n분석해줘."
        report, model = call_gemini(prompt)
        
        full_report += f"### 📌 {topic}\n{report}\n\n**[데이터 로그]**\n국내 {len(data['domestic'])}, 외신 {len(data['international'])}, 레딧 {len(data['reddit'])}\n모델: {model}\n\n---\n"

    # 메일 발송 섹션
    user, pw = get_env("GMAIL_USER"), get_env("GMAIL_PW")
    if user and pw:
        msg = MIMEMultipart()
        msg['Subject'] = f"🌐 [완료] {datetime.now().strftime('%m/%d')} 통합 보고서"
        msg['From'] = user; msg['To'] = user
        msg.attach(MIMEText(full_report, 'plain'))
        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(user, pw)
                server.sendmail(user, user, msg.as_string())
            print("✅ 메일 발송 성공!")
        except Exception as e: print(f"❌ 메일 발송 실패: {e}")
    else:
        print("❌ 메일 설정(Secrets)이 없습니다. 콘솔 출력:\n", full_report)

# ❗ 이 부분이 있어야 코드가 돌아갑니다
if __name__ == "__main__":
    main_process()
