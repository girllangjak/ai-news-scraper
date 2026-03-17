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
    
    # 1. 원어민 투자자 키워드 생성 (더 단순하게!)
    q_prompt = f"""
    Topic: '{topic}'
    Generate English search keywords for Reddit and Global News.
    - google_en: Professional news query
    - reddit_keywords: 3 very simple keywords (e.g. ['NVDA', 'stocks', 'investing'])
    Return JSON: {{"google_en": "...", "reddit_keywords": ["kw1", "kw2", "kw3"]}}
    """
    q_res, _ = call_gemini(q_prompt, is_json=True)
    
    q_data = {"google_en": topic, "reddit_keywords": [topic]}
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

    # 4. [핵심 수정] 레딧 강력 수집 (User-Agent 및 검색 방식 변경)
    # 일반적인 봇 차단을 피하기 위해 실제 브라우저인 척 위장합니다.
    reddit_headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    }
    
    for kw in q_data.get('reddit_keywords', []):
        try:
            # r/all 대신 전체 검색 결과에서 'Hot' 포스트 위주로 수집
            r_url = f"https://www.reddit.com/search.json?q={quote(kw)}&sort=hot&limit=5"
            r_res = requests.get(r_url, headers=reddit_headers, timeout=15)
            
            if r_res.status_code == 200:
                posts = r_res.json().get('data', {}).get('children', [])
                for p in posts:
                    title = p['data']['title']
                    ups = p['data']['ups'] # 추천 수 추가로 신뢰도 확보
                    results["reddit"].append(f"({kw}) {title} [👍{ups}]")
            
            if len(results["reddit"]) >= 10: break
            time.sleep(1) # 차단 방지를 위한 짧은 휴식
        except Exception as e:
            print(f"Reddit Error ({kw}): {e}")
            continue
        
    return results

def main_process():
    repo, token = get_env("GITHUB_REPOSITORY"), get_env("GH_TOKEN")
    issues = [{"title": "미국 주식 상위 10개 종목"}]
    if repo and token:
        try:
            res = requests.get(f"https://api.github.com/repos/{repo}/issues?state=open", headers={"Authorization": f"token {token}"}).json()
            if isinstance(res, list) and res: issues = res
        except: pass

    full_report = f"☕ 안녕하세요 관리자님, 오늘의 글로벌 브리핑입니다.\n{datetime.now().strftime('%Y년 %m월 %d일')} 리포트를 배달해 드립니다.\n\n"
    full_report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for issue in issues:
        topic = issue['title']
        data = fetch_all_data(topic)
        
        prompt = f"""
        주제: {topic}
        [데이터 소스]
        - 국내: {data['domestic']}
        - 해외 뉴스: {data['international']}
        - 레딧 여론: {data['reddit']}
        
        당신은 고급 비즈니스 뉴스레터 편집장입니다. 아래 지침을 지켜 작성하세요.
        1. 🌟 [오늘의 핵심 요약]
        2. 🌡️ [시장 온도차]: 한국 vs 해외 시각 분석.
        3. 💬 [레딧의 시선]: 실제 수집된 데이터({data['reddit']})를 바탕으로 구체적인 반응을 번역해서 포함할 것. 데이터가 적더라도 있는 내용을 충실히 반영.
        4. 💡 [인사이트]
        """
        report, model = call_gemini(prompt)
        
        full_report += f"📍 주제: {topic}\n\n{report}\n\n"
        full_report += "──────────────────────────────\n"
        full_report += f"📊 소스 트래킹: 국내 {len(data['domestic'])} / 외신 {len(data['international'])} / 레딧 {len(data['reddit'])}\n"
        full_report += f"🤖 분석 모델: {model}\n\n"

    full_report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n오늘도 성공적인 하루 되세요! 🦾"

    user, pw = get_env("GMAIL_USER"), get_env("GMAIL_PW")
    if user and pw:
        msg = MIMEMultipart()
        msg['Subject'] = f"✉️ [Global Watch] {datetime.now().strftime('%m/%d')} 리포트"
        msg['From'] = msg['To'] = user
        msg.attach(MIMEText(full_report, 'plain'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(user, pw)
            server.sendmail(user, user, msg.as_string())
        print("✅ 리포트 발송 완료!")

if __name__ == "__main__":
    main_process()
