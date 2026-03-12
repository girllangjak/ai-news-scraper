import requests
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 1. 설정 관리
CONFIG = {
    "NAVER_ID": os.environ.get("NAVER_ID"),
    "NAVER_SECRET": os.environ.get("NAVER_SECRET"),
    "GMAIL_USER": os.environ.get("GMAIL_USER"),
    "GMAIL_PW": os.environ.get("GMAIL_PW"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"),
    "REPO": "girllangjak/ai-news-scraper",
    "SEARCH_LIMIT": 20,
    "FINAL_COUNT": 5,
}

def get_target_topic():
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {"Authorization": f"token {CONFIG['GH_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        return res[0]['title'] if res and isinstance(res, list) else "오늘의 주요 뉴스"
    except: return "오늘의 주요 뉴스"

def get_ai_summary(title):
    """구글 AI 스튜디오 최신 규격 적용"""
    if not CONFIG["GEMINI_API_KEY"]: return "API 키 미설정"
    
    # 안정적인 v1beta 경로 사용
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"뉴스 제목: '{title}'\n이 뉴스 제목의 핵심 내용을 한국어로 1문장으로 요약해줘."
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        res = response.json()
        if 'candidates' in res and len(res['candidates']) > 0:
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # 에러 메시지 상세 확인용
        return f"요약 실패: {res.get('error', {}).get('message', '알 수 없는 에러')[:20]}"
    except:
        return "통신 지연으로 요약 불가"

def fetch_news(query):
    """검색 정교화: 검색어와 밀접한 뉴스만 추출"""
    # 검색어 정교화 (반드시 기사 제목에 검색어가 포함되도록 + 필수 연산자 사용)
    refined_query = f"{query} -광고 -홍보"
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(refined_query)}&display={CONFIG['SEARCH_LIMIT']}&sort=sim"
    headers = {"X-Naver-Client-Id": CONFIG['NAVER_ID'], "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']}
    
    try:
        items = requests.get(url, headers=headers, timeout=10).json().get('items', [])
        results = []
        seen = set()

        for item in items:
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
            
            # 검색어가 제목에 아예 없는 기사는 제외 (정교화 로직)
            keyword = query.split()[0] # 검색어의 첫 단어 (예: 이란)
            if keyword not in title: continue

            fingerprint = title.replace(" ", "")[:10]
            if fingerprint not in seen:
                summary = get_ai_summary(title)
                results.append({"title": title, "link": item['link'], "summary": summary})
                seen.add(fingerprint)
            
            if len(results) >= CONFIG['FINAL_COUNT']: break
        return results
    except: return []

if __name__ == "__main__":
    topic = get_target_topic()
    news_list = fetch_news(topic)
    
    today = datetime.now().strftime('%Y-%m-%d')
    content = [f"🤖 AI 분석관 리포트: {topic}\n", "="*50]
    
    if not news_list:
        content.append(f"'{topic}'(으)로 검색된 정교한 기사가 없습니다. 주제를 더 구체적으로 적어주세요.")
    else:
        for i, news in enumerate(news_list, 1):
            content.append(f"[{i}] {news['title']}")
            content.append(f"📝 요약: {news['summary']}")
            content.append(f"🔗 링크: {news['link']}\n")
    
    content.append("="*50)

    msg = MIMEMultipart()
    msg['From'], msg['To'] = CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [AI 요약] {today} - {topic}"
    msg.attach(MIMEText("\n".join(content), 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
        server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
    print("✅ 발송 완료")
