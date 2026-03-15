import requests
import smtplib
import os
import xml.etree.ElementTree as ET
import json
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from urllib.parse import quote

# 1. 환경 설정
CONFIG = {
    "NAVER": {"ID": os.environ.get("NAVER_ID"), "SEC": os.environ.get("NAVER_SECRET")},
    "MAIL": {"USER": os.environ.get("GMAIL_USER"), "PW": os.environ.get("GMAIL_PW")},
    "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "REPO": "girllangjak/ai-news-scraper"
}

TIER1_DOMAINS = ["reuters.com", "bloomberg.com", "wsj.com", "ft.com", "apnews.com", "nytimes.com", "economist.com", "theverge.com", "techcrunch.com"]

def clean_html(text):
    return re.sub('<.*?>|&([a-z0-9]+|#[0-9]{1,6});', '', text).strip() if text else ""

def get_issue_topic():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}"}
    try:
        res = requests.get(url, headers=headers).json()
        return res[0]['title'] if isinstance(res, list) and len(res) > 0 else None
    except: return None

def call_gemini(prompt):
    """
    [극대화된 오류 보고 모드]
    추출 데이터는 생략하고, 즉시 수정이 가능하도록 API 내부 정보를 무지비하게 상세히 기록함.
    """
    # 2026 스테이블 경로인 v1으로 변경하여 404 원천 차단 시도
    base_url = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"
    url = f"{base_url}?key={CONFIG['GEMINI_KEY']}"
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    debug_info = {
        "timestamp": datetime.now().isoformat(),
        "target_endpoint": base_url,
        "api_version": "v1",
        "model_requested": "gemini-1.5-flash",
        "request_headers": {k: v for k, v in headers.items()},
        "env_check": {
            "API_KEY_EXISTS": bool(CONFIG['GEMINI_KEY']),
            "API_KEY_LENGTH": len(CONFIG['GEMINI_KEY']) if CONFIG['GEMINI_KEY'] else 0
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        res_data = response.json()
        
        if response.status_code == 200 and 'candidates' in res_data:
            return res_data['candidates'][0]['content']['parts'][0]['text'].strip(), True
        
        # [상세 오류 보고서 작성]
        error_report = [
            "🚨 [CRITICAL API ERROR REPORT]",
            "="*50,
            f"STATUS_CODE: {response.status_code}",
            f"ERROR_TYPE: {res_data.get('error', {}).get('status', 'UNKNOWN')}",
            f"ERROR_MESSAGE: {res_data.get('error', {}).get('message', 'No message')}",
            "="*50,
            "[DEBUG CONTEXT]",
            json.dumps(debug_info, indent=2),
            "="*50,
            "[FULL JSON RESPONSE]",
            json.dumps(res_data, indent=2),
            "="*50,
            "💡 이 리포트를 AI에게 전달하면 즉시 수정 코드가 생성됩니다."
        ]
        return "\n".join(error_report), False

    except Exception as e:
        return f"🚨 SYSTEM_CRITICAL_FAILURE: {str(e)}\nCONTEXT: {json.dumps(debug_info)}", False

def fetch_news(topic):
    news_data = {"KR": [], "Global": []}
    seen_titles = set()
    limit_time = datetime.now() - timedelta(days=3)

    # 국내 수집
    n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=20&sort=date"
    n_headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
    try:
        items = requests.get(n_url, headers=n_headers, timeout=20).json().get('items', [])
        for it in items:
            title = clean_html(it['title'])
            if title[:15] not in seen_titles and len(news_data["KR"]) < 5:
                seen_titles.add(title[:15])
                news_data["KR"].append({"src": "국내언론", "title": title, "link": it['link']})
    except: pass

    # 해외 수집
    g_query = f"{topic} (" + " OR ".join([f"site:{d}" for d in TIER1_DOMAINS]) + ") when:3d"
    g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        root = ET.fromstring(requests.get(g_url, timeout=20).text)
        for it in root.findall('.//item'):
            title = it.find('title').text
            if title[:15] not in seen_titles and len(news_data["Global"]) < 5:
                seen_titles.add(title[:15])
                news_data["Global"].append({"src": title.split(" - ")[-1] if " - " in title else "외신", "title": title.split(" - ")[0], "link": it.find('link').text})
    except: pass
    
    return news_data

if __name__ == "__main__":
    today = datetime.now().strftime('%Y-%m-%d')
    target = get_issue_topic()

    if target:
        news = fetch_news(target)
        all_news = news["KR"] + news["Global"]
        
        if all_news:
            prompt = f"다음 뉴스를 분석하라. 데이터: {json.dumps(all_news, ensure_ascii=False)}"
            result_text, is_success = call_gemini(prompt)
            
            # 메일 발송 구성
            msg = MIMEMultipart()
            msg['Subject'] = f"{'📅' if is_success else '🚨'} [Report] {today} - {target}"
            msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
            
            # 성공 시 결과+링크, 실패 시 오류 리포트만 발송
            content = result_text if not is_success else f"{result_text}\n\n🔗 [Reference]\n" + "\n".join([f"- {n['src']}: {n['link']}" for n in all_news])
            msg.attach(MIMEText(content, 'plain'))

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
                server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
