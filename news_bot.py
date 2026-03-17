import requests
import smtplib
import os
import xml.etree.ElementTree as ET
import json
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

# [환경 설정] 2026년 최신 모델 우선순위
MODEL_PRIORITY = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-1.5-flash-latest"]

CONFIG = {
    "NAVER": {"ID": os.environ.get("NAVER_ID"), "SEC": os.environ.get("NAVER_SECRET")},
    "MAIL": {"USER": os.environ.get("GMAIL_USER"), "PW": os.environ.get("GMAIL_PW")},
    "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "REPO": "girllangjak/ai-news-scraper"
}

def call_gemini(prompt, is_json=False):
    """Gemini API 호출 및 Fallback 로직"""
    for model in MODEL_PRIORITY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={CONFIG['GEMINI_KEY']}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"} if is_json else {"temperature": 0.2}
        }
        try:
            res = requests.post(url, json=payload, timeout=45)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip(), True
        except: continue
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
    """
    res, success = call_gemini(prompt, is_json=True)
    try:
        return json.loads(res).get("countries", []) if success else []
    except: return []

def fetch_news_data(topic, countries):
    """국내(3일이내) 및 해외(현지어 검색/3일이내) 뉴스 수집"""
    limit = datetime.now(timezone.utc) - timedelta(days=3)
    results = {"domestic": [], "international": []}
    
    # 1. 국내 뉴스 (네이버)
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=15&sort=date"
        headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
        items = requests.get(n_url, headers=headers).json().get('items', [])
        for it in items:
            p_date = datetime.strptime(it['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').replace(tzinfo=timezone(timedelta(hours=9)))
            if p_date >= limit:
                results["domestic"].append({"title": re.sub('<.*?>', '', it['title']), "link": it['link']})
    except: pass

    # 2. 해외 뉴스 (AI 생성 현지어 쿼리 활용)
    for c in countries:
        search_q = c.get('query', topic)
        print(f"🌍 {c['name']} 현지 검색 시도: {search_q}")
        g_url = f"https://news.google.com/rss/search?q={quote(search_q)}+when:3d&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
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
        except: continue
            
    return results

def analyze_topic(topic):
    """수집된 데이터를 바탕으로 한국어 심층 분석 리포트 생성"""
    countries = get_target_countries_and_queries(topic)
    news_data = fetch_news_data(topic, countries)
    
    if not news_data["domestic"] and not news_data["international"]:
        return f"### 📌 주제: {topic}\n- 최근 72시간 내 관련 보도가 없습니다.\n", []

    prompt = f"""
    주제: {topic}
    데이터: {json.dumps(news_data, ensure_ascii=False)}
    
    지침:
    1. 반드시 한국어로만 작성할 것.
    2. [현지 보도 분석]: 관련 국가({', '.join([c['name'] for c in countries])})의 시각을 번역 요약.
    3. [국내외 시각 차이]: 한국 보도와 현지 보도의 온도 차이를 정밀 분석.
    4. [결론]: 상황을 3줄로 요약.
    5. '고준희 에코백' 같은 무관한 기사는 무시할 것.
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
        all_refs = []
        
        for issue in issues:
            topic = issue['title']
            report, links = analyze_topic(topic)
            full_body += f"{report}\n\n---\n"
            all_refs.extend(links)

        # 2. 통합 이메일 발송
        msg = MIMEMultipart()
        msg['Subject'] = f"🌐 [인텔리전스] 오늘자 주요 이슈 {len(issues)}건 분석 보고"
        msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
        
        ref_text = "\n\n🔗 [참조 링크 모음]\n" + "\n".join([f"- {l['title']}: {l['link']}" for l in all_refs])
        msg.attach(MIMEText(full_body + ref_text, 'plain'))
        
        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
                server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
            print(f"✅ 총 {len(issues)}건의 리포트 발송 완료!")
        except Exception as e:
            print(f"❌ 이메일 발송 실패: {e}")
