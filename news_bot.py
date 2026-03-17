from datetime import datetime, timedelta, timezone
from urllib.parse import quote

# [환경 설정] 2026년 최신 모델 우선순위
# [환경 설정] 모델 우선순위
MODEL_PRIORITY = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-1.5-flash-latest"]

CONFIG = {
@@ -21,7 +21,6 @@
}

def call_gemini(prompt, is_json=False):
    """Gemini API 호출 및 Fallback 로직"""
for model in MODEL_PRIORITY:
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={CONFIG['GEMINI_KEY']}"
payload = {
@@ -36,94 +35,81 @@ def call_gemini(prompt, is_json=False):
return "", False

def get_target_countries_and_queries(topic):
    """AI가 주제를 분석해 연관 국가와 '현지어 검색어' 생성"""
prompt = f"""
    주제 '{topic}'에 대해 심층 국제 뉴스를 수집하려 합니다.
    밀접한 연관 국가 3곳을 선정하고, 각 국가 뉴스 사이트에서 직접 검색할 '현지어 검색어'를 포함해 JSON으로 응답하세요.
    반드시 영어권(US)과 핵심 분쟁/관련국을 포함해야 합니다.
    
    응답 형식:
    {{ "countries": [
        {{ "name": "국가명", "hl": "언어코드", "gl": "지역코드", "query": "현지어검색어" }}
    ] }}
    주제 '{topic}'에 대해 국제 뉴스를 수집하려 함. 
    연관 국가 3곳과 해당 국가 언어로 된 '현지어 검색어'를 포함해 JSON으로 응답해.
    반드시 영어권(US)과 핵심 관련국을 포함할 것.
    형식: {{ "countries": [{{ "name": "국가명", "hl": "언어코드", "gl": "지역코드", "query": "현지어검색어" }}] }}
   """
res, success = call_gemini(prompt, is_json=True)
    try:
        return json.loads(res).get("countries", []) if success else []
    try: return json.loads(res).get("countries", []) if success else []
except: return []

def fetch_news_data(topic, countries):
    """국내(3일이내) 및 해외(현지어 검색/3일이내) 뉴스 수집"""
    limit = datetime.now(timezone.utc) - timedelta(days=3)
    """3일 이내 우선 수집, 부족 시 과거 데이터로 10개 충원"""
    limit_3d = datetime.now(timezone.utc) - timedelta(days=3)
results = {"domestic": [], "international": []}

    # 1. 국내 뉴스 (네이버)
    # 1. 국내 뉴스 (네이버) - 최대 10개 확보 시도
try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=15&sort=date"
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=50&sort=date"
headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
items = requests.get(n_url, headers=headers).json().get('items', [])
        
        # 날짜순으로 정렬되어 있으므로 순차적으로 담음 (최신 우선)
for it in items:
            p_date = datetime.strptime(it['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').replace(tzinfo=timezone(timedelta(hours=9)))
            if p_date >= limit:
                results["domestic"].append({"title": re.sub('<.*?>', '', it['title']), "link": it['link']})
            title = re.sub('<.*?>', '', it['title'])
            results["domestic"].append({"title": title, "link": it['link']})
            if len(results["domestic"]) >= 10: break
except: pass

    # 2. 해외 뉴스 (AI 생성 현지어 쿼리 활용)
    # 2. 해외 뉴스 (국가별 구글 RSS) - 국가당 3~4개씩 총 10개 확보 시도
for c in countries:
search_q = c.get('query', topic)
        print(f"🌍 {c['name']} 현지 검색 시도: {search_q}")
        g_url = f"https://news.google.com/rss/search?q={quote(search_q)}+when:3d&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
        g_url = f"https://news.google.com/rss/search?q={quote(search_q)}&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
try:
root = ET.fromstring(requests.get(g_url, timeout=15).text)
            count = 0
for it in root.findall('.//item'):
                g_date = datetime.strptime(it.find('pubDate').text, '%a, %d %b %Y %H:%M:%S GMT').replace(tzinfo=timezone.utc)
                if g_date >= limit:
                    results["international"].append({
                        "country": c['name'],
                        "title": it.find('title').text,
                        "link": it.find('link').text
                    })
                    count += 1
                if count >= 3: break
                results["international"].append({
                    "country": c['name'],
                    "title": it.find('title').text,
                    "link": it.find('link').text
                })
                # 전체 10개 차면 중단 (국가별 균형보다 수량 우선)
                if len(results["international"]) >= 10: break
            if len(results["international"]) >= 10: break
except: continue

return results

def analyze_topic(topic):
    """수집된 데이터를 바탕으로 한국어 심층 분석 리포트 생성"""
countries = get_target_countries_and_queries(topic)
news_data = fetch_news_data(topic, countries)

if not news_data["domestic"] and not news_data["international"]:
        return f"### 📌 주제: {topic}\n- 최근 72시간 내 관련 보도가 없습니다.\n", []
        return f"### 📌 주제: {topic}\n- 검색된 기사가 전혀 없습니다.\n", []

    # AI 분석 프롬프트 (최신성 강조 및 요약 지침)
prompt = f"""
   주제: {topic}
    데이터: {json.dumps(news_data, ensure_ascii=False)}
    기사 데이터: {json.dumps(news_data, ensure_ascii=False)}
   
   지침:
    1. 반드시 한국어로만 작성할 것.
    2. [현지 보도 분석]: 관련 국가({', '.join([c['name'] for c in countries])})의 시각을 번역 요약.
    3. [국내외 시각 차이]: 한국 보도와 현지 보도의 온도 차이를 정밀 분석.
    4. [결론]: 상황을 3줄로 요약.
    5. '고준희 에코백' 같은 무관한 기사는 무시할 것.
    1. 반드시 한국어로 작성.
    2. [현지 시각 분석]: 수집된 기사를 바탕으로 각국의 시각을 요약. 
    3. [국내외 시각 차이]: 보도 경향 분석. 
    4. 만약 기사 발행일이 3일을 초과한 과거 기사라면 '과거 기록 기반 분석'임을 명시할 것.
   """
report, success = call_gemini(prompt)
links = news_data["domestic"] + news_data["international"]
return report if success else f"### 📌 주제: {topic}\n- AI 분석 실패\n", links

if __name__ == "__main__":
    print("🚀 글로벌 뉴스 스크랩 봇 가동 시작")
    
    # 1. GitHub 모든 Open 이슈 가져오기
issue_url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
issues = requests.get(issue_url, headers={"Authorization": f"token {CONFIG['GH_TOKEN']}"}).json()

    if not issues or not isinstance(issues, list):
        print("🛑 처리할 이슈가 없습니다.")
    else:
        full_body = f"## 📅 {datetime.now().strftime('%Y-%m-%d')} 글로벌 뉴스 분석 보고서\n\n"
    if issues and isinstance(issues, list):
        full_body = f"## 📅 {datetime.now().strftime('%Y-%m-%d')} 글로벌 통합 리포트\n\n"
all_refs = []

for issue in issues:
@@ -132,18 +118,23 @@ def analyze_topic(topic):
full_body += f"{report}\n\n---\n"
all_refs.extend(links)

        # 2. 통합 이메일 발송
        # 메일 발송
msg = MIMEMultipart()
        msg['Subject'] = f"🌐 [인텔리전스] 오늘자 주요 이슈 {len(issues)}건 분석 보고"
        msg['Subject'] = f"🌐 [분석보고] 등록된 이슈 {len(issues)}건에 대한 통합 리포트"
msg['From'] = msg['To'] = CONFIG['MAIL']['USER']

        ref_text = "\n\n🔗 [참조 링크 모음]\n" + "\n".join([f"- {l['title']}: {l['link']}" for l in all_refs])
        # 참조 링크 10개씩 구분하여 정리
        ref_text = "\n\n🔗 [참조 링크 모음]\n"
        for issue in issues:
            topic = issue['title']
            ref_text += f"\n[{topic} 관련 기사]\n"
            # 해당 이슈에 대한 링크만 필터링하거나 전체 나열
            for l in all_refs:
                ref_text += f"- {l['title']}: {l['link']}\n"
        
msg.attach(MIMEText(full_body + ref_text, 'plain'))

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
                server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
            print(f"✅ 총 {len(issues)}건의 리포트 발송 완료!")
        except Exception as e:
            print(f"❌ 이메일 발송 실패: {e}")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
            server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
        print(f"✅ {len(issues)}건 분석 완료 및 메일 발송.")
