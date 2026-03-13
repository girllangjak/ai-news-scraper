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

# 환경 설정
CONFIG = {
    "NAVER": {"ID": os.environ.get("NAVER_ID"), "SEC": os.environ.get("NAVER_SECRET")},
    "MAIL": {"USER": os.environ.get("GMAIL_USER"), "PW": os.environ.get("GMAIL_PW")},
    "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "REPO": "girllangjak/ai-news-scraper"
}

def clean_html(text):
    return re.sub('<.*?>|&([a-z0-9]+|#[0-9]{1,6});', '', text).strip() if text else ""

def get_issue_topic():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}"}
    try:
        res = requests.get(url, headers=headers).json()
        return res[0]['title'] if res else "이란 전쟁"
    except: return "이란 전쟁"

def call_gemini(prompt):
    """
    모든 오류를 상세히 노출하는 분석 함수
    """
    # 현재 가장 유력한 v1beta 엔드포인트
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_KEY']}"
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    debug_info = {
        "request_url": url.replace(CONFIG['GEMINI_KEY'], "REDACTED_KEY"),
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        status_code = response.status_code
        
        try:
            res_data = response.json()
        except:
            res_data = {"raw_text": response.text}

        # 1. 성공 시
        if status_code == 200 and 'candidates' in res_data:
            return res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # 2. 실패 시 - 오류 내용을 상세하게 구성
        error_report = [
            "❌ [Gemini API 호출 실패 보고서]",
            f"1. HTTP Status: {status_code}",
            f"2. Debug Context: {json.dumps(debug_info)}",
            "3. Full Response Data:",
            json.dumps(res_data, indent=2, ensure_ascii=False),
            "-------------------------------------------",
            "위 내용을 복사해서 Gemini에게 전달해 주세요."
        ]
        return "\n".join(error_report)

    except Exception as e:
        return f"❌ 시스템 치명적 예외 발생: {str(e)}"

def fetch_news(topic):
    news_data = []
    seen = set()
    limit_time = datetime.now() - timedelta(days=3)

    # 네이버
    n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=30&sort=date"
    n_headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
    try:
        items = requests.get(n_url, headers=n_headers, timeout=20).json().get('items', [])
        for it in items:
            p_date = datetime.strptime(it['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
            if p_date < limit_time: continue
            title = clean_html(it['title'])
            if title[:15] not in seen:
                seen.add(title[:15])
                news_data.append({"src": "Pending", "title": title, "date": p_date.strftime('%Y-%m-%d'), "link": it['link']})
    except: pass

    # 구글
    g_query = f"{topic} news when:3d"
    g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        root = ET.fromstring(requests.get(g_url, timeout=20).text)
        for it in root.findall('.//item')[:10]:
            title = it.find('title').text
            if title[:15] not in seen:
                seen.add(title[:15])
                src = title.split(" - ")[-1] if " - " in title else "Global"
                news_data.append({"src": src, "title": title.split(" - ")[0], "date": "최근 3일", "link": it.find('link').text})
    except: pass
    
    return news_data

if __name__ == "__main__":
    today = datetime.now().strftime('%Y-%m-%d')
    target = get_issue_topic()
    collected = fetch_news(target)

    if not collected:
        report_body = "최근 3일간 수집된 데이터가 없습니다."
    else:
        prompt = f"다음 뉴스를 한국어로 요약해. 데이터:\n{json.dumps(collected[:15], ensure_ascii=False)}"
        report_body = call_gemini(prompt)

    links = "\n\n🔗 [수집된 원문 리스트]\n"
    for c in collected:
        domain = c['link'].split('/')[2].replace('www.', '')
        links += f"- {c['src'] if c['src'] != 'Pending' else domain}: {c['link']}\n"

    msg = MIMEMultipart()
    msg['Subject'] = f"📅 [Debug Report] {today} - {target} 분석 시도"
    msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
    msg.attach(MIMEText(report_body + links, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
            server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
        print(f"✅ {today} 프로세스 완료")
    except Exception as e:
        print(f"❌ 메일 전송 실패: {e}")
