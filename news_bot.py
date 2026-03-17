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

# 2026년 최신 모델 설정
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
            res = requests.post(url, json=payload, timeout=45)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip(), True
        except: continue
    return "", False

def get_target_countries(topic):
    """주제에 따른 타겟 국가 자동 선정"""
    prompt = f"'{topic}' 이슈와 밀접한 국가 3곳의 명칭, 언어코드(hl), 지역코드(gl)를 JSON으로 줘. 예: {{\"countries\": [{{ \"name\": \"Israel\", \"hl\": \"iw\", \"gl\": \"IL\" }}]}}"
    res, success = call_gemini(prompt, is_json=True)
    try: return json.loads(res).get("countries", []) if success else []
    except: return []

def fetch_news_data(topic, countries):
    """국내 및 다국어 해외 뉴스 수집 (72시간 이내)"""
    limit = datetime.now(timezone.utc) - timedelta(days=3)
    results = {"domestic": [], "international": []}
    
    # 국내 뉴스 (네이버)
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=10&sort=date"
        headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
        items = requests.get(n_url, headers=headers).json().get('items', [])
        for it in items:
            p_date = datetime.strptime(it['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').replace(tzinfo=timezone(timedelta(hours=9)))
            if p_date >= limit:
                results["domestic"].append({"title": re.sub('<.*?>', '', it['title']), "link": it['link']})
    except: pass

    # 해외 뉴스 (국가별 구글 RSS)
    for c in countries:
        g_url = f"https://news.google.com/rss/search?q={quote(topic)}+when:3d&hl={c['hl']}&gl={c['gl']}&ceid={c['gl']}:{c['hl']}"
        try:
            root = ET.fromstring(requests.get(g_url, timeout=15).text)
            for it in root.findall('.//item')[:3]:
                g_date = datetime.strptime(it.find('pubDate').text, '%a, %d %b %Y %H:%M:%S GMT').replace(tzinfo=timezone.utc)
                if g_date >= limit:
                    results["international"].append({"country": c['name'], "title": it.find('title').text, "link": it.find('link').text})
        except: continue
    return results

def process_issue(topic):
    """개별 이슈 분석 및 리포트 생성"""
    print(f"🔎 주제 분석 시작: {topic}")
    countries = get_target_countries(topic)
    news_data = fetch_news_data(topic, countries)
    
    if not news_data["domestic"] and not news_data["international"]:
        return f"### {topic}\n- 최근 3일 이내 관련 뉴스가 없습니다.\n", []

    prompt = f"""
    주제: {topic}
    데이터: {json.dumps(news_data, ensure_ascii=False)}
    
    지침:
    1. 한국어로 작성. 
    2. [현지 시각 분석] 섹션: 각 국가별 보도 내용을 번역 요약. (없으면 '없음' 표기)
    3. [시각 차이] 섹션: 한국과 현지 보도의 차이점 분석.
    4. [결론] 섹션: 상황 요약.
    5. 주제와 무관한 광고성 기사나 인물 동정은 제외할 것.
    """
    report, success = call_gemini(prompt)
    links = news_data["domestic"] + news_data["international"]
    return report if success else f"### {topic}\n- 분석 실패\n", links

if __name__ == "__main__":
    # 1. 모든 Open 이슈 가져오기
    issue_url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    issues = requests.get(issue_url, headers={"Authorization": f"token {CONFIG['GH_TOKEN']}"}).json()
    
    if issues and isinstance(issues, list):
        full_report = f"## 📅 글로벌 뉴스 통합 분석 리포트 ({datetime.now().strftime('%Y-%m-%d')})\n\n"
        all_links = []
        
        # 2. 각 이슈별 루프 실행
        for issue in issues:
            topic = issue['title']
            report_part, links = process_issue(topic)
            full_report += report_part + "\n---\n"
            all_links.extend(links)

        # 3. 통합 이메일 발송
        msg = MIMEMultipart()
        msg['Subject'] = f"🌐 [뉴스 봇] 오늘자 {len(issues)}건의 주요 분석 리포트"
        msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
        
        link_section = "\n\n🔗 [참조 링크 모음]\n" + "\n".join([f"- {l['title']}: {l['link']}" for l in all_links])
        msg.attach(MIMEText(full_report + link_section, 'plain'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
            server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
        print(f"✅ 총 {len(issues)}건의 리포트 발송 완료!")
