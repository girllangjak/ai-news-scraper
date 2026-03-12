name: Daily News Bot

on:
  schedule:
    - cron: '0 0 * * *' # 매일 아침 실행 (필요시 조정)
  workflow_dispatch: # 수동 실행 버튼 활성화

jobs:
  build:
    runs-on: ubuntu-latest
    env:
      # Node.js 24 강제 사용 설정 (경고 문구 해결)
      FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true
    
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4
        with:
          # 봇이 깃허브에 접근할 때 사용할 신분증을 명시합니다.
          token: ${{ secrets.GH_TOKEN }}

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests

      - name: Run News Bot
        env:
          NAVER_ID: ${{ secrets.NAVER_ID }}
          NAVER_SECRET: ${{ secrets.NAVER_SECRET }}
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_PW: ${{ secrets.GMAIL_PW }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: python news_bot.py
