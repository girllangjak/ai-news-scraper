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

# 최신 모델 설정
MODEL_PRIORITY = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-1.5-flash-latest"]

CONFIG = {
    "NAVER": {"ID": os.environ.get("NAVER_ID"), "SEC": os.environ.get("NAVER_SECRET")},
    "MAIL": {"USER": os.environ.get("GMAIL_USER"), "PW": os.environ.get("GMAIL_PW")},
    "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "REPO": "girllangjak/ai-news-scraper"
}

def call_gemini(prompt, is_json=False):
    for model in MODEL_PRIORITY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={CONFIG['GEMINI_KEY']}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"} if is_json else {}
        }
        try:
            res = requests.post(url, json=payload, timeout=40)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip(), True
        except: continue
    return "", False

def get_target_countries(topic):
    """AI를 통해 키워드 관련 국가 3곳 선정"""
    prompt = f"'{topic}'와 밀접한 국가 3곳과 언어(hl), 지역(gl) 코드를 JSON으로 줘. 예: {{\"countries\": [{{ \"name\": \"Israel\", \"hl\": \"iw\", \"gl\": \"IL\" }}]}}"
    res, success = call_gemini(prompt, is_json=True)
    try: return json.loads(res).get("countries", []) if success else []
    except: return []

def fetch_naver_news(topic):
    """국내 뉴스: 3일 이내 기사만 필터링"""
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=20&sort=date"
    headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
    news_list = []
    limit = datetime.now(timezone.utc) - timedelta(days=3)
    
    try:
        items = requests.get(url, headers=headers).json().get('items', [])
        for it in items:
            # 네이버 pubDate: Tue, 17 Mar 2026 10:00:00 +0900
            p_date = datetime.strptime(it['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').replace(tzinfo=timezone(timedelta(hours=9)))
            if p_date >= limit:
                news_list.append({"src": "국내", "title": re.sub('<.*?>', '', it['title']), "link": it['link']})
        return news_list[:5]
    except: return []

def fetch_global_news(topic, countries):
    """해외 뉴스: 현지 언어 검색 및 3일 이내 필터링"""
    global_news = []
    limit = datetime.now(timezone.utc) - timedelta(days=3)
    
    for c in countries:
        g_url = f"https://news.google.com/rss/search?q={quote(topic)}+when:3d&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
        try:
            root = ET.fromstring(requests.get(g_url, timeout=20).text)
            for it in root.findall('.//item')[:3]:
                # 구글 pubDate: Tue, 17 Mar 2026 01:00:00 GMT
                g_date = datetime.strptime(it.find('pubDate').text, '%a, %d %b %Y %H:%M:%S GMT').replace(tzinfo=timezone.utc)
                if g_date >= limit:
                    global_news.append({"country": c['name'], "title": it.find('title').text, "link": it.find('link').text})
        except: continue
    return global_news

if __name__ == "__main__":
    # GitHub 이슈에서 주제 가져오기
    issue_url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    res = requests.get(issue_url, headers={"Authorization": f"token {CONFIG['GH_TOKEN']}"}).json()
    
    if res and isinstance(res, list):
        topic = res[0]['title']
        countries = get_target_countries(topic)
        
        kr_news = fetch_naver_news(topic)
        intl_news = fetch_global_news(topic, countries)
        
        # 분석 요청 (해외 뉴스 부재 시 처리 지침 포함)
        all_data = {"domestic": kr_news, "international": intl_news}
        analysis_prompt = f"""
        주제: {topic}
        기사 데이터: {json.dumps(all_data, ensure_ascii=False)}
        
        지침:
        1. 한국어로 작성. 72시간 이내의 최신 기사만 분석에 포함할 것.
        2. 해외 기사가 없다면 '해외 현지 보도 없음'으로 간략히 표기.
        3. 주제와 무관한 기사(예: 유명인 단순 근황 등)는 분석에서 배제할 것.
        4. 국내와 해외 시각 차이를 분석하고 3줄 결론을 낼 것.
        """
        report, success = call_gemini(analysis_prompt)

        if success:
            msg = MIMEMultipart()
            msg['Subject'] = f"🌐 [글로벌 리포트] {topic} ({datetime.now().strftime('%m/%d')})"
            msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
            ref_links = "\n".join([f"- {n['title']}: {n['link']}" for n in kr_news + intl_news])
            msg.attach(MIMEText(f"{report}\n\n--- 수집 링크 ---\n{ref_links}", 'plain'))
            
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
                server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
            print(f"✅ {topic} 리포트 발송 완료")
