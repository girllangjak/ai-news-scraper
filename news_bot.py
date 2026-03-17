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
            "generationConfig": {
                "response_mime_type": "application/json" if is_json else "text/plain",
                "temperature": 0.1 # 분석의 일관성을 위해 온도를 낮췄습니다.
            }
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
    
    # 1. 쿼리 생성 로직 강화 (영어 키워드 추출 강조)
    q_prompt = f"""
    Topic: {topic}
    Generate 2 focus countries and their local search queries in JSON.
    CRITICAL: For 'reddit_query', provide a very simple 1-2 word English keyword (e.g., 'Nvidia', 'Stock market') to ensure results.
    Format: {{"countries": [{{"name": "USA", "hl": "en", "gl": "US", "query": "...", "reddit_query": "..."}}]}}
    """
    q_res, _ = call_gemini(q_prompt, is_json=True)
    countries = [{"name": "USA", "hl": "en", "gl": "US", "query": topic, "reddit_query": topic}]
    if q_res:
        try:
            start_idx = q_res.find('{')
            end_idx = q_res.rfind('}') + 1
            countries = json.loads(q_res[start_idx:end_idx]).get("countries", countries)
        except: pass

    # 2. 네이버 뉴스
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=10"
        headers = {"X-Naver-Client-Id": get_env("NAVER_ID"), "X-Naver-Client-Secret": get_env("NAVER_SECRET")}
        n_res = requests.get(n_url, headers=headers).json().get('items', [])
        results["domestic"] = [re.sub('<.*?>', '', i['title']) for i in n_res]
    except: pass

    # 3. 구글 외신 (RSS)
    for c in countries:
        try:
            g_url = f"https://news.google.com/rss/search?q={quote(c['query'])}&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
            res = requests.get(g_url, timeout=10)
            titles = re.findall(r'<title>(.*?)</title>', res.text)[1:6]
            results["international"].extend([f"[{c['name']}] {t}" for t in titles])
        except: continue

    # 4. 레딧 여론 (단순화된 영어 키워드 사용)
    headers = {"User-Agent": "Mozilla/5.0"}
    for sub in ["wallstreetbets", "stocks", "investing"]:
        r_query = countries[0].get('reddit_query', topic)
        try:
            r_url = f"https://www.reddit.com/r/{sub}/search.json?q={quote(r_query)}&restrict_sr=1&sort=relevance&limit=5"
            r_res = requests.get(r_url, headers=headers, timeout=10).json()
            posts = [p['data']['title'] for p in r_res.get('data', {}).get('children', [])]
            results["reddit"].extend([f"({sub}) {p}" for p in posts])
        except: continue
        
    return results

def main_process():
    repo, token = get_env("GITHUB_REPOSITORY"), get_env("GH_TOKEN")
    issues = [{"title": "미국 증시 및 기술주 동향"}] # 기본값
    if repo and token:
        try:
            issue_url = f"https://api.github.com/repos/{repo}/issues?state=open"
            res = requests.get(issue_url, headers={"Authorization": f"token {token}"}).json()
            if isinstance(res, list) and len(res) > 0: issues = res
        except: pass

    full_report = f"## 📅 {datetime.now().strftime('%Y-%m-%d')} 글로벌 인텔리전스 리포트\n\n"

    for issue in issues:
        topic = issue['title']
        print(f"🔎 멀티 소스 분석 중: {topic}")
        data = fetch_all_data(topic)
        
        # 분석 프롬프트 강화
        prompt = f"""
        주제: {topic}
        [데이터 소스]
        - 국내 뉴스: {data['domestic']}
        - 해외 외신: {data['international']}
        - 레딧 여론: {data['reddit']}
        
        분석 지침:
        1. 한국과 해외 시장의 반응 차이를 반드시 포함할 것.
        2. 레딧의 실시간 분위기를 요약에 녹일 것.
        3. 투자자가 주의해야 할 리스크를 언급할 것.
        한국어로 5줄 내외로 깊이 있게 요약해줘.
        """
        report, model = call_gemini(prompt)
        
        full_report += f"### 📌 {topic}\n{report}\n\n"
        full_report += f"**[데이터 수집 현황]**\n- 국내: {len(data['domestic'])}건, 외신: {len(data['international'])}건, 레딧: {len(data['reddit'])}건\n- 모델: {model}\n\n---\n"

    # 메일 발송
    user, pw = get_env("GMAIL_USER"), get_env("GMAIL_PW")
    if user and pw:
        msg = MIMEMultipart()
        msg['Subject'] = f"🌐 [Intelligence] {datetime.now().strftime('%m/%d')} 분석 보고서"
        msg['From'] = msg['To'] = user
        msg.attach(MIMEText(full_report, 'plain'))
        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(user, pw)
                server.sendmail(user, user, msg.as_string())
            print("✅ 메일 발송 성공!")
        except Exception as e: print(f"❌ 발송 실패: {e}")

if __name__ == "__main__":
    main_process()
