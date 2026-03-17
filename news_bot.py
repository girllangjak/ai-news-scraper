import requests, smtplib, os, json, re, time
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# [관리자님 전용 2026년형 모델 리스트]
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
            "generationConfig": {"response_mime_type": "application/json" if is_json else "text/plain", "temperature": 0.1}
        }
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip(), model
        except: continue
    return None, "All Models Failed"

def fetch_all_data(topic):
    """국내 뉴스(한국어) + 구글 외신(현지어) + 레딧(영어) 통합 수집"""
    results = {"domestic": [], "international": [], "reddit": []}
    
    # 1. 쿼리 생성 로직: 한국어 주제를 현지 전문 용어로 번역/확장
    q_prompt = f"""
    당신은 전문 리서치 어시스턴트입니다. 다음 한국어 주제를 분석하기 위해 해외 검색용 키워드를 생성하세요.
    주제: {topic}
    
    JSON 형식으로만 응답하세요:
    {{
      "queries": {{
        "google_en": "구글 뉴스 검색용 전문 영어 쿼리 (예: 'semiconductor market outlook 2026')",
        "reddit_en": "레딧 검색용 짧고 강력한 영어 키워드 (예: 'NVDA', 'stocks')",
        "google_jp": "일본 시장 관련 시 쿼리 (없으면 빈칸)"
      }}
    }}
    """
    q_res, _ = call_gemini(q_prompt, is_json=True)
    
    # 기본값 설정 (에러 대비)
    q_data = {"google_en": topic, "reddit_en": topic} 
    if q_res:
        try:
            start_idx = q_res.find('{')
            end_idx = q_res.rfind('}') + 1
            q_data = json.loads(q_res[start_idx:end_idx]).get("queries", q_data)
        except: pass

    # 2. 국내 뉴스 (네이버 - 한국어 검색)
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=10"
        headers = {"X-Naver-Client-Id": get_env("NAVER_ID"), "X-Naver-Client-Secret": get_env("NAVER_SECRET")}
        n_res = requests.get(n_url, headers=headers).json().get('items', [])
        results["domestic"] = [re.sub('<.*?>', '', i['title']) for i in n_res]
    except: pass

    # 3. 구글 외신 (AI가 생성한 영어 쿼리로 검색)
    en_query = q_data.get("google_en", topic)
    try:
        g_url = f"https://news.google.com/rss/search?q={quote(en_query)}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(g_url, timeout=10)
        titles = re.findall(r'<title>(.*?)</title>', res.text)[1:11]
        results["international"].extend([f"[Global] {t}" for t in titles])
    except: pass

    # 4. 레딧 여론 (AI가 생성한 짧은 영어 키워드로 검색)
    re_query = q_data.get("reddit_en", topic)
    headers = {"User-Agent": "Mozilla/5.0"}
    for sub in ["wallstreetbets", "stocks", "investing"]:
        try:
            r_url = f"https://www.reddit.com/r/{sub}/search.json?q={quote(re_query)}&restrict_sr=1&sort=new&limit=5"
            r_res = requests.get(r_url, headers=headers, timeout=10).json()
            posts = [p['data']['title'] for p in r_res.get('data', {}).get('children', [])]
            results["reddit"].extend([f"({sub}) {p}" for p in posts])
        except: continue
        
    return results

def main_process():
    repo, token = get_env("GITHUB_REPOSITORY"), get_env("GH_TOKEN")
    issues = [{"title": "글로벌 증시 및 주요 종목 분석"}]
    if repo and token:
        try:
            issue_url = f"https://api.github.com/repos/{repo}/issues?state=open"
            res = requests.get(issue_url, headers={"Authorization": f"token {token}"}).json()
            if isinstance(res, list) and len(res) > 0: issues = res
        except: pass

    full_report = f"## 📅 {datetime.now().strftime('%Y-%m-%d')} 글로벌 인텔리전스 리포트\n\n"

    for issue in issues:
        topic = issue['title']
        print(f"🔎 전략적 다국어 수집 중: {topic}")
        data = fetch_all_data(topic)
        
        prompt = f"""
        당신은 글로벌 투자 전략가입니다. 다음 데이터를 종합하여 리포트를 작성하세요.
        주제: {topic}
        [국내 뉴스]: {data['domestic']}
        [해외 외신]: {data['international']}
        [레딧 여론]: {data['reddit']}
        
        지침:
        1. 국내외 시각 차이를 '온도 차이'라는 항목으로 분석할 것.
        2. 레딧의 서양 개미(투자자)들 반응을 생생하게 전달할 것.
        3. 한국어로 전문성 있게 작성할 것.
        """
        report, model = call_gemini(prompt)
        
        full_report += f"### 📌 {topic}\n{report}\n\n"
        full_report += f"**[데이터 수집 로그]**\n- 국내: {len(data['domestic'])}건\n- 해외(영어 검색): {len(data['international'])}건\n- 레딧(현지 커뮤니티): {len(data['reddit'])}건\n- 분석 모델: {model}\n\n---\n"

    # 메일 발송
    user, pw = get_env("GMAIL_USER"), get_env("GMAIL_PW")
    if user and pw:
        msg = MIMEMultipart()
        msg['Subject'] = f"🌐 [Intelligence] 글로벌 통합 분석 완료"
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
