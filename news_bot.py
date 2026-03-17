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
            "generationConfig": {"response_mime_type": "application/json" if is_json else "text/plain", "temperature": 0.1}
        }
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip(), model
        except: continue
    return None, "All Models Failed"

def fetch_all_data(topic):
    results = {"domestic": [], "international": [], "reddit": []}
    
    # 1. [핵심 수정] 검색 최적화: 한국어 주제를 '원어민 투자자 키워드'로 변환
    q_prompt = f"""
    주제: '{topic}'
    이 주제를 분석하기 위해 해외 검색용 키워드를 생성하세요.
    - google_query: 뉴스 검색용 (예: 'S&P 500 top 10 stocks 2026 analysis')
    - reddit_keywords: 레딧 검색용 짧은 단어 리스트 (예: ['NVDA', 'MSFT', 'Top10', 'stocks'])
    
    JSON 응답: {{"google_query": "...", "reddit_keywords": ["kw1", "kw2"]}}
    """
    q_res, _ = call_gemini(q_prompt, is_json=True)
    
    # 기본값 설정
    en_query = topic
    re_keywords = [topic]
    if q_res:
        try:
            start_idx = q_res.find('{')
            end_idx = q_res.rfind('}') + 1
            q_data = json.loads(q_res[start_idx:end_idx])
            en_query = q_data.get("google_query", topic)
            re_keywords = q_data.get("reddit_keywords", [topic])
        except: pass

    # 2. 국내 뉴스 (한국어)
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=10"
        headers = {"X-Naver-Client-Id": get_env("NAVER_ID"), "X-Naver-Client-Secret": get_env("NAVER_SECRET")}
        n_res = requests.get(n_url, headers=headers).json().get('items', [])
        results["domestic"] = [re.sub('<.*?>', '', i['title']) for i in n_res]
    except: pass

    # 3. 구글 외신 (번역된 영어 쿼리)
    try:
        g_url = f"https://news.google.com/rss/search?q={quote(en_query)}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(g_url, timeout=10)
        titles = re.findall(r'<title>(.*?)</title>', res.text)[1:11]
        results["international"].extend([f"[Global News] {t}" for t in titles])
    except: pass

    # 4. [강화] 레딧 여론 (AI가 뽑은 여러 키워드로 반복 검색)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for kw in re_keywords[:3]: # 상위 3개 키워드로 검색
        try:
            r_url = f"https://www.reddit.com/r/all/search.json?q={quote(kw)}&limit=5&sort=relevance"
            r_res = requests.get(r_url, headers=headers, timeout=10).json()
            posts = [f"({kw}) {p['data']['title']}" for p in r_res.get('data', {}).get('children', [])]
            results["reddit"].extend(posts)
            if len(results["reddit"]) >= 10: break # 최대 10건
        except: continue
        
    return results

def main_process():
    repo, token = get_env("GITHUB_REPOSITORY"), get_env("GH_TOKEN")
    # GitHub 이슈에서 주제 가져오기 (없으면 기본값)
    issues = [{"title": "미국 주식 상위 10개 종목"}]
    if repo and token:
        try:
            res = requests.get(f"https://api.github.com/repos/{repo}/issues?state=open", 
                               headers={"Authorization": f"token {token}"}).json()
            if isinstance(res, list) and res: issues = res
        except: pass

    full_report = f"## 📅 {datetime.now().strftime('%Y-%m-%d')} 글로벌 통합 리포트\n\n"

    for issue in issues:
        topic = issue['title']
        data = fetch_all_data(topic)
        
        # 분석 요청 (수집된 영어 데이터를 한글로 분석하라고 명시)
        prompt = f"""
        주제: {topic}
        [국내 데이터]: {data['domestic']}
        [해외 외신(영어)]: {data['international']}
        [레딧 여론(영어)]: {data['reddit']}
        
        당신은 다국어 분석가입니다. 위 영어 데이터들을 한국어로 번역/요약하여 
        '국내 vs 해외 온도 차이'와 '서양 투자자들의 생생한 목소리'를 리포트로 작성하세요.
        """
        report, model = call_gemini(prompt)
        
        full_report += f"### 📌 {topic}\n{report}\n\n"
        full_report += f"**[데이터 로그]**\n- 국내: {len(data['domestic'])}, 해외뉴스: {len(data['international'])}, 레딧: {len(data['reddit'])}\n- 모델: {model}\n\n---\n"

    # 메일 발송
    user, pw = get_env("GMAIL_USER"), get_env("GMAIL_PW")
    if user and pw:
        msg = MIMEMultipart()
        msg['Subject'] = f"🌐 [Intelligence] {datetime.now().strftime('%m/%d')} 리포트"
        msg['From'] = msg['To'] = user
        msg.attach(MIMEText(full_report, 'plain'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(user, pw)
            server.sendmail(user, user, msg.as_string())
        print("✅ 발송 성공")

if __name__ == "__main__":
    main_process()
