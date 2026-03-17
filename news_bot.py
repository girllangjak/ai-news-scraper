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

# 2026년 최신 모델 리스트
MODEL_PRIORITY = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-1.5-flash-latest"]

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
    print(f"📡 GitHub API 호출 중: {CONFIG['REPO']}")
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}"}
    try:
        res = requests.get(url, headers=headers)
        print(f"🔎 GitHub 응답 코드: {res.status_code}")
        issues = res.json()
        if isinstance(issues, list) and len(issues) > 0:
            return issues[0]['title']
        return None
    except Exception as e:
        print(f"❌ GitHub 호출 에러: {e}")
        return None

def call_gemini(prompt):
    for model in MODEL_PRIORITY:
        print(f"🧠 Gemini 호출 시도 중... (모델: {model})")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={CONFIG['GEMINI_KEY']}"
        headers = {'Content-Type': 'application/json'}
        payload = {"contents": [{"parts": [{"text": f"반드시 한국어로 응답해라: {prompt}"}]}]}
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=40)
            if response.status_code == 200:
                print(f"✅ Gemini 응답 성공 ({model})")
                return response.json()['candidates'][0]['content']['parts'][0]['text'].strip(), True
            print(f"⚠️ {model} 실패: {response.status_code}")
        except Exception as e:
            print(f"⚠️ {model} 에러: {e}")
            continue
    return "분석 실패", False

def fetch_news(topic):
    news_data = {"KR": [], "Global": []}
    seen_titles = set()
    limit_time = datetime.now() - timedelta(days=3)
    print(f"📰 뉴스 수집 시작: '{topic}' (기준: {limit_time})")

    # 국내 (네이버)
    try:
        n_url = f"https://openapi.naver.com/v1/search/news.json?query={quote(topic)}&display=20&sort=date"
        n_headers = {"X-Naver-Client-Id": CONFIG['NAVER']['ID'], "X-Naver-Client-Secret": CONFIG['NAVER']['SEC']}
        items = requests.get(n_url, headers=n_headers).json().get('items', [])
        for it in items:
            title = clean_html(it['title'])
            if title[:15] not in seen_titles and len(news_data["KR"]) < 5:
                seen_titles.add(title[:15])
                news_data["KR"].append({"src": "국내", "title": title, "link": it['link']})
        print(f"   - 국내 기사 수집 완료: {len(news_data['KR'])}개")
    except Exception as e:
        print(f"   - 네이버 호출 에러: {e}")

    # 해외 (구글)
    try:
        g_query = f'"{topic}" (lens OR brand) when:3d'
        g_url = f"https://news.google.com/rss/search?q={quote(g_query)}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(g_url)
        root = ET.fromstring(res.text)
        for it in root.findall('.//item')[:10]:
            title = it.find('title').text
            if len(news_data["Global"]) < 5:
                news_data["Global"].append({"src": "외신", "title": title, "link": it.find('link').text})
        print(f"   - 해외 기사 수집 완료: {len(news_data['Global'])}개")
    except Exception as e:
        print(f"   - 구글 호출 에러: {e}")
    
    return news_data

if __name__ == "__main__":
    print("--- 봇 가동 시작 ---")
    target = get_issue_topic()
    print(f"📌 최종 키워드: {target}")

    if not target:
        print("🛑 종료: 처리할 키워드가 없습니다. (GitHub Issues 확인 요망)")
    else:
        news = fetch_news(target)
        all_items = news["KR"] + news["Global"]
        
        if not all_items:
            print(f"🛑 종료: '{target}'에 대한 최근 3일치 기사가 0개입니다.")
        else:
            print(f"🔄 총 {len(all_items)}개 기사 분석 시작...")
            res_text, success = call_gemini(json.dumps(all_items, ensure_ascii=False))
            
            if success:
                print("📨 메일 발송 중...")
                msg = MIMEMultipart()
                msg['Subject'] = f"📅 [완료] {target} 글로벌 분석"
                msg['From'] = msg['To'] = CONFIG['MAIL']['USER']
                msg.attach(MIMEText(res_text, 'plain'))
                
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(CONFIG['MAIL']['USER'], CONFIG['MAIL']['PW'])
                    server.sendmail(CONFIG['MAIL']['USER'], CONFIG['MAIL']['USER'], msg.as_string())
                print("✅ 모든 작업이 완료되었습니다!")
            else:
                print("❌ 분석 결과 생성 실패로 메일을 보내지 못했습니다.")
    print("--- 봇 가동 종료 ---")
