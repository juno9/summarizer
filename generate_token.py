"""
Google Drive API 토큰 생성 스크립트

사용법:
1. .env 파일에 DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET 설정
   또는 credentials/google_credentials.json 파일 준비
2. 이 스크립트 실행: python generate_token.py
3. 브라우저에서 Google 계정 로그인 및 권한 승인
4. credentials/token.json 파일이 생성됨
5. docker-compose restart 로 컨테이너 재시작
"""

import os
import json
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

# .env 파일 로드
load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDS_PATH = 'credentials/google_credentials.json'
TOKEN_PATH = 'credentials/token.json'

def get_client_config():
    """환경변수 또는 JSON 파일에서 클라이언트 설정 가져오기"""

    # 1. 환경변수에서 확인
    client_id = os.getenv('DRIVE_CLIENT_ID')
    client_secret = os.getenv('DRIVE_CLIENT_SECRET')

    if client_id and client_secret:
        print(f"환경변수에서 클라이언트 정보 로드")
        print(f"  Client ID: {client_id[:20]}...")
        return {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }

    # 2. JSON 파일에서 확인
    if os.path.exists(CREDS_PATH):
        print(f"JSON 파일에서 클라이언트 정보 로드: {CREDS_PATH}")
        with open(CREDS_PATH, 'r') as f:
            return json.load(f)

    return None

def main():
    # credentials 폴더 생성
    os.makedirs('credentials', exist_ok=True)

    creds = None

    # 기존 토큰 확인
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        print(f"기존 토큰 발견: {TOKEN_PATH}")

    # 토큰이 없거나 만료된 경우
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("토큰 갱신 중...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"토큰 갱신 실패: {e}")
                print("새 토큰을 발급받습니다...\n")
                creds = None

        if not creds or not creds.valid:
            client_config = get_client_config()

            if not client_config:
                print("\n[오류] Google OAuth 클라이언트 정보가 없습니다.")
                print("\n방법 1: .env 파일에 설정")
                print("  DRIVE_CLIENT_ID=your_client_id")
                print("  DRIVE_CLIENT_SECRET=your_client_secret")
                print("\n방법 2: JSON 파일 다운로드")
                print("  1. https://console.cloud.google.com 접속")
                print("  2. APIs & Services > Credentials")
                print("  3. OAuth 2.0 Client ID 생성 (Desktop app)")
                print("  4. Download JSON")
                print(f"  5. 파일을 {CREDS_PATH} 로 저장")
                return

            print("\n브라우저에서 Google 계정 인증을 진행합니다...")
            print("(브라우저가 자동으로 열립니다)\n")

            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)

        # 토큰 저장
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
        print(f"\n[완료] 토큰 저장 완료: {TOKEN_PATH}")

    print("\n" + "="*50)
    print("인증 성공!")
    print("="*50)
    print("\n다음 명령으로 Docker 컨테이너를 재시작하세요:")
    print("\n  docker-compose restart")
    print("\n또는 새로 빌드:")
    print("\n  docker-compose up --build -d")

if __name__ == '__main__':
    main()
