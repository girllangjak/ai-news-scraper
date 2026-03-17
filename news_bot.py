import requests, smtplib, os, json, re, time, random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# [관리자님 전용 2026년형 모델 리스트]
MODEL_PRIORITY = ["gemini-3.1-flash-lite-preview", "gemini-3.1-pro-preview", "gemini-2.5-flash"]

def get_env(key):
    """환경 변수 안전하게 가져오기"""
    return os.environ.get(key, "")

def call_gemini(prompt, is_json=False):
    """Gemini API 호출 - 우선순위 모델 자동 스위칭 포함"""
    key = get_env("GEMINI_API_KEY")
    if not key: return None, "No API Key"
    
    for model in MODEL_PRIORITY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json" if is_json else "text/plain",
                "temperature": 0.2
            }
        }
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                return data['candidates'][0]['content']['parts'][0]['text'].strip(), model
        except:
            continue # 다음 모델로 시도
    return None, "All Models Failed"

def fetch_all_data(topic):
    """국내(Naver) + 국외(Google) + 커뮤니티(Reddit) 데이터 통합 수집"""
    results = {"domestic": [], "international": [], "reddit": []}
    
    # 1. 지능형 쿼리 생성 (레딧용 영어 키워드 추출 필수)
    q_prompt = f"""
    당신은 전문 리서처입니다. 주제 '{topic}'에 대해 해외 분석을 수행하기 위한 키워드를 생성하세요.
    - google_en: 외신 검색용 영어 문장
    - reddit_kw: 레딧 검색용 핵심 영어 단어 (예: 'NVDA', 'stock market')
    JSON 형식으로만 응답: {{"google_en": "...", "reddit_kw": "..."}}
    """
    q_res, _ = call_gemini(q_prompt, is_json=True)
    q_data = {"google_en": topic, "reddit_kw": topic}
    if q_res:
        try:
            start = q_res.find('{'); end = q_res.rfind('}') + 1
            q_data = json.loads(q_res[start:end])
        except: pass

    # 2. 국내 뉴스 수집 (네이버 API)
    naver_id = get_env("NAVER_ID")
    naver_secret = get_env("NAVER_SECRET")
    if naver_id and naver_secret:
        try:
            n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=10"
            headers = {"X-Naver-Client-Id": naver_id, "X-Naver-Client-Secret": naver_secret}
            n_res = requests.get(n_url, headers=headers).json()
            results["domestic"] = [re.sub('<.*?>', '', item['title']) for item in n_res.get('items', [])]
        except: pass

    # 3. 해외 외신 수집 (Google News RSS)
    try:
        g_url = f"https://news.google.com/rss/search?q={quote(q_data['google_en'])}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(g_url, timeout=10)
        # XML 타이틀 추출 (첫 번째는 채널명이므로 제외)
        results["international"] = re.findall(r'<title>(.*?)</title>', res.text)[1:11]
    except: pass

    # 4. [플랜 B] 레딧 우회 수집 (공식 API 미사용 버전)
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Version/115.0.0.0 Safari/537.36"
    ]
    r_kw = q_data.get('reddit_kw', topic)
    r_url = f"https://www.reddit.com/search.json?q={quote(r_kw)}&sort=relevance&t=day&limit=7"
    headers = {"User-Agent": random.choice(user_agents)}
    
    try:
        r_res = requests.get(r_url, headers=headers, timeout=15)
        if r_res.status_code == 200:
            posts = r_res.json().get('data', {}).get('children', [])
            results["reddit"] = [f"{p['data']['title']} (👍{p['data']['ups']})" for p in posts]
        time.sleep(1.5) # 속도 제한 방지
    except: pass
        
    return results

def main_process():
    # GitHub 이슈 연동 (프로젝트 관리용)
    repo = get_env("GITHUB_REPOSITORY")
    token = get_env("GH_TOKEN")
    issues = [{"title": "미국 주식 상위 10개 종목"}] # 기본값
    
    if repo and token:
        try:
            issue_url = f"https://api.github.com/repos/{repo}/issues?state=open"
            res = requests.get(issue_url, headers={"Authorization": f"token {token}"}).json()
            if isinstance(res, list) and len(res) > 0:
                issues = res
        except: pass

    # 이메일 리포트 작성 시작
    full_report = f"☕ 안녕하세요 관리자님, 오늘의 글로벌 인텔리전스입니다.\n{datetime.now().strftime('%Y년 %m월 %d일')} 리포트를 배달해 드립니다.\n\n"
    full_report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for issue in issues:
        topic = issue['title']
        print(f"🔎 분석 시작: {topic}")
        data = fetch_all_data(topic)
        
        # 비즈니스 매거진 스타일 분석 프롬프트
        prompt = f"""
        주제: {topic}
        [데이터 소스]
        - 국내: {data['domestic']}
        - 해외 뉴스: {data['international']}
        - 레딧 여론: {data['reddit']}
        
        당신은 고급 비즈니스 뉴스레터 편집장입니다. 다음 구조로 작성하세요:
        1. 🌟 [오늘의 핵심 요약]: 전체 상황을 임팩트 있게.
        2. 🌡️ [시장 온도차]: 국내 vs 해외의 시각 차이 분석.
        3. 💬 [레딧의 시선]: 수집된 {len(data['reddit'])}건의 레딧 반응을 번역하여 생생하게 전달.
        4. 💡 [전략적 인사이트]: 관리자님을 위한 맞춤형 제언.
        문체는 친절하고 전문적인 비즈니스 톤을 유지하세요.
        """
        report, model = call_gemini(prompt)
        
        full_report += f"📍 주제: {topic}\n\n{report}\n\n"
        full_report += "──────────────────────────────\n"
        full_report += f"📊 소스 트래킹: 국내 {len(data['domestic'])} / 외신 {len(data['international'])} / 레딧 {len(data['reddit'])}\n"
        full_report += f"🤖 분석 모델: {model}\n\n"

    full_report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n오늘도 성공적인 비즈니스 데이 되시길 바랍니다! 🦾"

    # 이메일 발송 (Gmail)
    user = get_env("GMAIL_USER")
    pw = get_env("GMAIL_PW")
    if user and pw:
        msg = MIMEMultipart()
        msg['Subject'] = f"✉️ [Global Watch] {datetime.now().strftime('%m/%d')} 리포트 도착"
        msg['From'] = msg['To'] = user
        msg.attach(MIMEText(full_report, 'plain'))
        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(user, pw)
                server.sendmail(user, user, msg.as_string())
            print("✅ 메일 발송 성공!")
        except Exception as e:
            print(f"❌ 발송 실패: {e}")

if __name__ == "__main__":
    main_process()
