import requests, smtplib, os, json, re, time, random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# [모델 우선순위]
MODEL_PRIORITY = ["gemini-3.1-flash-lite-preview", "gemini-3.1-pro-preview", "gemini-2.5-flash"]

def get_env(key): return os.environ.get(key, "")

def call_gemini(prompt, is_json=False):
    key = get_env("GEMINI_API_KEY")
    if not key: return None, "No API Key"
    for model in MODEL_PRIORITY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"response_mime_type": "application/json" if is_json else "text/plain", "temperature": 0.2}}
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200: return res.json()['candidates'][0]['content']['parts'][0]['text'].strip(), model
        except: continue
    return None, "All Models Failed"

def fetch_stocktwits(ticker):
    """Stocktwits 공개 API 우회 수집 (키 불필요)"""
    twits = []
    if not ticker: ticker = "SPY"
    try:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json?limit=10"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(url, headers=headers, timeout=10).json()
        for msg in res.get('messages', []):
            sentiment = msg.get('entities', {}).get('sentiment', {}).get('basic', 'Neutral')
            body = re.sub(r'http\S+', '', msg['body']) # 링크 제거
            twits.append(f"[{sentiment}] {body[:100]}...")
    except: pass
    return twits

def fetch_investing_titles(query):
    """구글 뉴스 인덱싱을 통한 Investing.com 여론 우회 수집"""
    investing_data = []
    try:
        # site:investing.com 쿼리를 통해 인베스팅 내의 뉴스/댓글 기반 소식을 가져옵니다.
        search_url = f"https://www.google.com/search?q=site:investing.com+{quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(search_url, headers=headers, timeout=10)
        # 구글 검색 결과의 제목 정규식 (클래스명 변화에 무관하게 h3 태그 타겟팅)
        titles = re.findall(r'h3.*?>(.*?)</h3>', res.text)
        for t in titles:
            clean_t = re.sub('<.*?>', '', t)
            if clean_t and len(clean_t) > 5:
                investing_data.append(clean_t)
    except: pass
    return investing_data[:7]

def fetch_all_data(topic):
    results = {"domestic": [], "international": [], "stocktwits": [], "investing": []}
    
    # 1. 티커 및 키워드 추출 (강력한 가이드)
    q_prompt = f"""
    Topic: '{topic}'
    Task: 1. 관련 미국 주식 티커 1개(예: NVDA) 2. 영어 뉴스 검색어 1개 생성.
    관련 티커가 모호하면 무조건 'SPY'를 반환하세요.
    JSON 형식: {{"ticker": "TICKER", "query": "search query"}}
    """
    q_res, _ = call_gemini(q_prompt, is_json=True)
    q_data = {"ticker": "SPY", "query": topic} # 기본값
    if q_res:
        try:
            match = re.search(r'\{.*\}', q_res, re.DOTALL)
            if match: q_data = json.loads(match.group())
        except: pass

    # 2. 국내 소식 (Naver)
    n_id, n_sec = get_env("NAVER_ID"), get_env("NAVER_SECRET")
    if n_id and n_sec:
        try:
            n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=10"
            n_res = requests.get(n_url, headers={"X-Naver-Client-Id": n_id, "X-Naver-Client-Secret": n_sec}).json()
            results["domestic"] = [re.sub('<.*?>', '', i['title']) for i in n_res.get('items', [])]
        except: pass

    # 3. 글로벌 외신 (Google News)
    try:
        g_url = f"https://news.google.com/rss/search?q={quote(q_data['query'])}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(g_url, timeout=10)
        results["international"] = re.findall(r'<title>(.*?)</title>', res.text)[1:11]
    except: pass

    # 4. 신규 소스 수집 (Stocktwits & Investing)
    results["stocktwits"] = fetch_stocktwits(q_data['ticker'])
    results["investing"] = fetch_investing_titles(q_data['query'])
        
    return results

def main_process():
    repo, token = get_env("GITHUB_REPOSITORY"), get_env("GH_TOKEN")
    issues = [{"title": "미국 시장 주요 이슈"}] # 기본 주제
    if repo and token:
        try:
            res = requests.get(f"https://api.github.com/repos/{repo}/issues?state=open", headers={"Authorization": f"token {token}"}).json()
            if isinstance(res, list) and res: issues = res
        except: pass

    full_report = f"☕ 안녕하세요 관리자님, 글로벌 마켓 인텔리전스입니다.\n{datetime.now().strftime('%Y년 %m월 %d일')} 브리핑을 시작합니다.\n\n"
    full_report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for issue in issues:
        topic = issue['title']
        print(f"🔎 {topic} 분석 중...")
        data = fetch_all_data(topic)
        
        prompt = f"""
        주제: {topic}
        [데이터] 국내: {data['domestic']}, 외신: {data['international']}, 스톡트윗: {data['stocktwits']}, 인베스팅: {data['investing']}
        당신은 금융 전문 편집장입니다. 다음 구조로 상세히 리포트를 작성하세요.
        1. [마켓 써머리]: 핵심 이슈 요약
        2. [글로벌 민심]: 스톡트윗({len(data['stocktwits'])}건)과 인베스팅({len(data['investing'])}건) 데이터를 바탕으로 서양 개미들의 Bullish/Bearish 분위기를 생생하게 전달
        3. [종합 전략]: 국내외 시각 차이를 분석한 대응 방안
        세련된 비즈니스 한국어로 작성하세요.
        """
        report, model = call_gemini(prompt)
        
        full_report += f"📍 분석 주제: {topic}\n\n{report}\n\n"
        full_report += "──────────────────────────────\n"
        full_report += f"📊 데이터 트래킹: 국내 {len(data['domestic'])} / 외신 {len(data['international'])} / 스톡트윗 {len(data['stocktwits'])} / 인베스팅 {len(data['investing'])}\n"
        full_report += f"🤖 분석 모델: {model}\n\n"

    full_report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n성공적인 하루 되십시오! 🦾"

    user, pw = get_env("GMAIL_USER"), get_env("GMAIL_PW")
    if user and pw:
        msg = MIMEMultipart(); msg['Subject'] = f"✉️ [Global Insight] {datetime.now().strftime('%m/%d')} 리포트"; msg['From'] = msg['To'] = user
        msg.attach(MIMEText(full_report, 'plain'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(user, pw); server.sendmail(user, user, msg.as_string())
        print("✅ 메일 전송 완료!")

if __name__ == "__main__":
    main_process()
