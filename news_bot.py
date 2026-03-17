import requests, smtplib, os, json, re, time
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
            "generationConfig": {"response_mime_type": "application/json" if is_json else "text/plain", "temperature": 0.2}
        }
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip(), model
        except: continue
    return None, "All Models Failed"

def fetch_all_data(topic):
    results = {"domestic": [], "international": [], "reddit": []}
    
    # 1. 지능형 쿼리 생성 (영어 검색 최적화)
    q_prompt = f"""
    주제: '{topic}'
    이 주제를 분석하기 위해 원어민 투자자들이 사용하는 검색 키워드를 생성하세요.
    - google_en: 외신 뉴스용 (예: 'US market cap leaders 2026')
    - reddit_en: 커뮤니티용 짧은 키워드 리스트 (예: ['NVDA', 'Magnificent 7', 'Market sentiment'])
    응답은 반드시 JSON: {{"google_en": "...", "reddit_en": ["kw1", "kw2"]}}
    """
    q_res, _ = call_gemini(q_prompt, is_json=True)
    
    q_data = {"google_en": topic, "reddit_en": [topic]}
    if q_res:
        try:
            start = q_res.find('{'); end = q_res.rfind('}') + 1
            q_data = json.loads(q_res[start:end])
        except: pass

    # 2. 국내 소식 (Naver)
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=8"
        headers = {"X-Naver-Client-Id": get_env("NAVER_ID"), "X-Naver-Client-Secret": get_env("NAVER_SECRET")}
        n_res = requests.get(n_url, headers=headers).json().get('items', [])
        results["domestic"] = [re.sub('<.*?>', '', i['title']) for i in n_res]
    except: pass

    # 3. 글로벌 외신 (English News)
    try:
        g_url = f"https://news.google.com/rss/search?q={quote(q_data['google_en'])}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(g_url, timeout=10)
        results["international"] = re.findall(r'<title>(.*?)</title>', res.text)[1:9]
    except: pass

    # 4. 레딧 실시간 여론 (Multi-Keyword Search)
    headers = {"User-Agent": "Mozilla/5.0"}
    for kw in q_data.get('reddit_en', [])[:3]:
        try:
            r_url = f"https://www.reddit.com/r/all/search.json?q={quote(kw)}&limit=5&sort=hot"
            r_res = requests.get(r_url, headers=headers, timeout=10).json()
            posts = [f"[{kw}] {p['data']['title']}" for p in r_res.get('data', {}).get('children', [])]
            results["reddit"].extend(posts)
        except: continue
        
    return results

def main_process():
    repo, token = get_env("GITHUB_REPOSITORY"), get_env("GH_TOKEN")
    issues = [{"title": "글로벌 마켓 트렌드 및 주요 종목"}]
    if repo and token:
        try:
            res = requests.get(f"https://api.github.com/repos/{repo}/issues?state=open", headers={"Authorization": f"token {token}"}).json()
            if isinstance(res, list) and res: issues = res
        except: pass

    # 이메일 본문 시작 (HTML 스타일을 위한 줄바꿈 처리)
    full_report = f"☕ 안녕하세요 관리자님, 오늘의 글로벌 브리핑입니다.\n{datetime.now().strftime('%Y년 %m월 %d일')} 리포트를 배달해 드립니다.\n\n"
    full_report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for issue in issues:
        topic = issue['title']
        data = fetch_all_data(topic)
        
        # 분석 프롬프트 (양식을 예쁘게 만들도록 지시)
        prompt = f"""
        주제: {topic}
        [데이터 소스]
        - 국내: {data['domestic']}
        - 해외 뉴스: {data['international']}
        - 레딧 여론: {data['reddit']}
        
        당신은 고급 비즈니스 뉴스레터 편집장입니다. 아래 양식에 맞춰 한글로 리포트를 작성하세요.
        1. 🌟 [오늘의 핵심 요약]: 전체 상황을 한 눈에 보기 좋게.
        2. 🌡️ [시장 온도차]: 한국과 해외의 시각 차이 분석.
        3. 💬 [레딧의 시선]: 해외 투자자들의 실제 반응을 번역해서 포함.
        4. 💡 [인사이트]: 관리자님을 위한 맞춤 제언.
        문체는 친절하면서도 전문적으로 작성하세요.
        """
        report, model = call_gemini(prompt)
        
        full_report += f"📍 주제: {topic}\n\n{report}\n\n"
        full_report += "──────────────────────────────\n"
        full_report += f"📊 소스 트래킹: 국내 {len(data['domestic'])} / 외신 {len(data['international'])} / 레딧 {len(data['reddit'])}\n"
        full_report += f"🤖 분석 모델: {model}\n\n"

    full_report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    full_report += "오늘도 성공적인 비즈니스 데이 되시길 바랍니다! 🦾"

    # 메일 발송
    user, pw = get_env("GMAIL_USER"), get_env("GMAIL_PW")
    if user and pw:
        msg = MIMEMultipart()
        msg['Subject'] = f"✉️ [Global Watch] {datetime.now().strftime('%m/%d')} 리포트가 도착했습니다."
        msg['From'] = msg['To'] = user
        msg.attach(MIMEText(full_report, 'plain'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(user, pw)
            server.sendmail(user, user, msg.as_string())
        print("✅ 리포트 발송 완료!")

if __name__ == "__main__":
    main_process()
