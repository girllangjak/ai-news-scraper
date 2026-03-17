import requests, smtplib, os, json, re, time, random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 모델 우선순위 유지
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
    """Stocktwits API를 통해 종목별 실시간 트윗 및 심리 수집"""
    twits = []
    try:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json?limit=7"
        res = requests.get(url, timeout=10).json()
        for msg in res.get('messages', []):
            sentiment = msg.get('entities', {}).get('sentiment', {}).get('basic', 'Neutral')
            twits.append(f"[{sentiment}] {msg['body']}")
    except: pass
    return twits

def fetch_investing_news(query):
    """Investing.com의 뉴스 및 댓글 맥락 수집 (RSS 기반 우회)"""
    investing_data = []
    try:
        # 인베스팅은 스크래핑 차단이 강해, 뉴스 RSS를 통해 최신 논쟁 거리를 수집합니다.
        url = f"https://www.google.com/search?q=site:investing.com+{quote(query)}&tbm=nws"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(url, headers=headers, timeout=10)
        titles = re.findall(r'<div class="vv7cAc">(.*?)</div>', res.text) # 검색 결과 요약문 추출
        investing_data = titles[:5]
    except: pass
    return investing_data

def fetch_all_data(topic):
    results = {"domestic": [], "international": [], "stocktwits": [], "investing": []}
    
    # 1. 티커 및 키워드 추출
    q_prompt = f"주제 '{topic}'에서 관련 미국 주식 티커(예: NVDA) 1개와 영어 키워드를 뽑아주세요. JSON: {{\"ticker\": \"...\", \"query\": \"...\"}}"
    q_res, _ = call_gemini(q_prompt, is_json=True)
    q_data = {"ticker": "SPY", "query": topic} # 기본값
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

    # 3. 글로벌 외신 (Google News)
    try:
        g_url = f"https://news.google.com/rss/search?q={quote(q_data['query'])}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(g_url, timeout=10)
        results["international"] = re.findall(r'<title>(.*?)</title>', res.text)[1:9]
    except: pass

    # 4. Stocktwits & Investing 수집 (레딧 대체)
    results["stocktwits"] = fetch_stocktwits(q_data['ticker'])
    results["investing"] = fetch_investing_news(q_data['query'])
        
    return results

def main_process():
    repo, token = get_env("GITHUB_REPOSITORY"), get_env("GH_TOKEN")
    issues = [{"title": "미국 주식 상위 10개 종목"}]
    if repo and token:
        try:
            res = requests.get(f"https://api.github.com/repos/{repo}/issues?state=open", headers={"Authorization": f"token {token}"}).json()
            if isinstance(res, list) and res: issues = res
        except: pass

    full_report = f"☕ 안녕하세요 관리자님, 오늘의 글로벌 투자 리포트입니다.\n{datetime.now().strftime('%Y년 %m월 %d일')} 리포트를 배달해 드립니다.\n\n"
    full_report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for issue in issues:
        topic = issue['title']
        data = fetch_all_data(topic)
        
        prompt = f"""
        주제: {topic}
        [데이터 소스]
        - 국내: {data['domestic']}
        - 해외 뉴스: {data['international']}
        - 스톡트윗(실시간): {data['stocktwits']}
        - 인베스팅(이슈): {data['investing']}
        
        당신은 고급 투자 뉴스레터 편집장입니다. 
        Stocktwits의 Bullish(긍정)/Bearish(부정) 분위기를 포함하여, 
        전 세계 개미들의 최신 토론 내용을 한국어로 세련되게 요약하세요.
        """
        report, model = call_gemini(prompt)
        
        full_report += f"📍 주제: {topic}\n\n{report}\n\n"
        full_report += "──────────────────────────────\n"
        full_report += f"📊 트래킹: 국내 {len(data['domestic'])} / 외신 {len(data['international'])} / 스톡트윗 {len(data['stocktwits'])} / 인베스팅 {len(data['investing'])}\n"
        full_report += f"🤖 분석 모델: {model}\n\n"

    full_report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n오늘도 성투하시길 바랍니다! 🦾"

    user, pw = get_env("GMAIL_USER"), get_env("GMAIL_PW")
    if user and pw:
        msg = MIMEMultipart(); msg['Subject'] = f"✉️ [Market Intelligence] {datetime.now().strftime('%m/%d')} 리포트"; msg['From'] = msg['To'] = user
        msg.attach(MIMEText(full_report, 'plain'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(user, pw); server.sendmail(user, user, msg.as_string())
        print("✅ 발송 성공!")

if __name__ == "__main__":
    main_process()
