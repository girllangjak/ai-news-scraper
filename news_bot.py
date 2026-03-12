import requests
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

# 1. 설정 관리 (GitHub Secrets에 등록된 이름과 일치해야 합니다)
CONFIG = {
    "NAVER_ID": os.environ.get("NAVER_ID"),
    "NAVER_SECRET": os.environ.get("NAVER_SECRET"),
    "GMAIL_USER": os.environ.get("GMAIL_USER"),
    "GMAIL_PW": os.environ.get("GMAIL_PW"),
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"),
    "REPO": "girllangjak/ai-news-scraper",
    "FINAL_COUNT": 5,
}

def get_target_topic():
    """GitHub 이슈에서 검색 키워드 추출"""
    url = f"https://api.github.com/repos/{CONFIG['REPO']}/issues?state=open"
    headers = {
        "Authorization": f"token {CONFIG['GH_TOKEN']}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        if isinstance(res, list) and len(res) > 0:
            return res[0]['title']
        return "오늘의 주요 뉴스"
    except Exception as e:
        print(f"이슈 추출 실패: {e}")
        return "오늘의 주요 뉴스"

def get_ai_summary(title):
    """사용자가 AI Studio에서 직접 확인한 Gemini 3 Flash Preview 적용"""
    if not CONFIG["GEMINI_API_KEY"]:
        return "❌ 에러: GEMINI_API_KEY가 설정되지 않았습니다."
    
    # 직접 확인하신 최신 모델 ID와 v1beta 주소 조합
    model_id = "gemini-3-flash-preview"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={CONFIG['GEMINI_API_KEY']}"
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [{"text": f"다음 뉴스 제목을 읽고 핵심 내용을 한국어 한 문장으로 요약해줘: {title}"}]
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        res = response.json()
        
        if 'candidates' in res and len(res['candidates']) > 0:
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # 에러 발생 시 상세 사유 반환
        error_msg = res.get('error', {}).get('message', '알 수 없는 응답 구조')
        return f"❌ AI 요약 실패: {error_msg}"
    except Exception as e:
        return f"❌ 통신 장애: {str(e)[:30]}"

def fetch_refined_news(query):
    """네이버 뉴스 검색 및 정밀 필터링"""
    refined_query = f"{query} -광고 -홍보 -이벤트"
    url = f"https://openapi.naver.com/v1/search/news.json?query={quote(refined_query)}&display=20&sort=sim"
    headers = {
        "X-Naver-Client-Id": CONFIG['NAVER_ID'],
        "X-Naver-Client-Secret": CONFIG['NAVER_SECRET']
    }
    
    try:
        items = requests.get(url, headers=headers, timeout=10).json().get('items', [])
        results, seen = [], set()

        for item in items:
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
            
            # 제목에 검색어 키워드가 포함된 경우만 선별
            if any(word in title for word in query.split()):
                fingerprint = title.replace(" ", "")[:10]
                if fingerprint not in seen:
                    summary = get_ai_summary(title)
                    results.append({
                        "title": title,
                        "link": item['link'],
                        "summary": summary
                    })
                    seen.add(fingerprint)
            
            if len(results) >= CONFIG['FINAL_COUNT']:
                break
        return results
    except Exception as e:
        print(f"뉴스 수집 실패: {e}")
        return []

if __name__ == "__main__":
    # 1. 주제 파악
    topic = get_target_topic()
    
    # 2. 뉴스 수집 및 AI 요약
    news_list = fetch_refined_news(topic)
    
    # 3. 메일 본문 구성
    today = datetime.now().strftime('%Y-%m-%d')
    content = [
        f"🗞️ AI 분석 리포트: {topic}",
        f"📅 분석 일시: {datetime.now().strftime('%H:%M:%S')}",
        "="*50 + "\n"
    ]
    
    if not news_list:
        content.append(f"'{topic}'에 대한 정밀 분석 결과를 찾지 못했습니다.")
    else:
        for i, news in enumerate(news_list, 1):
            content.append(f"[{i}] {news['title']}")
            content.append(f"📝 AI 요약: {news['summary']}")
            content.append(f"🔗 링크: {news['link']}\n")
    
    content.append("="*50)
    content.append("※ 본 리포트는 Gemini 3 Flash Preview 모델로 분석되었습니다.")

    # 4. 메일 발송
    msg = MIMEMultipart()
    msg['From'] = CONFIG['GMAIL_USER']
    msg['To'] = CONFIG['GMAIL_USER']
    msg['Subject'] = f"📅 [AI 분석 리포트] {today} - {topic}"
    msg.attach(MIMEText("\n".join(content), 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CONFIG['GMAIL_USER'], CONFIG['GMAIL_PW'])
            server.sendmail(CONFIG['GMAIL_USER'], CONFIG['GMAIL_USER'], msg.as_string())
        print(f"✅ '{topic}' 리포트 발송 성공!")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")
