"""
구글 드라이브 업로드
환경변수 또는 JSON 파일에서 인증 정보 로드
"""
import os
import json
import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.file']

class GoogleDriveUploader:
    def __init__(self, config):
        self.config = config
        self.service = self._get_service()
        self.folder_id = config.google_drive_folder_id

    def _get_credentials_from_env(self):
        """환경변수에서 OAuth 클라이언트 정보 가져오기"""
        client_id = os.getenv('DRIVE_CLIENT_ID')
        client_secret = os.getenv('DRIVE_CLIENT_SECRET')

        if not client_id or not client_secret:
            return None

        # OAuth 클라이언트 설정 구조 생성
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }
        return client_config

    def _get_service(self):
        """구글 드라이브 API 서비스 생성"""
        creds = None
        token_path = '/app/credentials/token.json'
        creds_path = '/app/credentials/google_credentials.json'

        # 1. 기존 토큰 확인
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
                logger.info("기존 토큰 로드 완료")
            except Exception as e:
                logger.warning(f"토큰 로드 실패: {e}")

        # 2. 토큰이 없거나 만료된 경우
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("토큰 갱신 완료")
                    # 갱신된 토큰 저장
                    with open(token_path, 'w') as token:
                        token.write(creds.to_json())
                except Exception as e:
                    logger.error(f"토큰 갱신 실패: {e}")
                    creds = None

            if not creds:
                # 환경변수에서 클라이언트 정보 확인
                client_config = self._get_credentials_from_env()

                if client_config:
                    logger.info("환경변수에서 OAuth 클라이언트 정보 로드")
                    # 토큰이 없으면 생성 필요
                    if not os.path.exists(token_path):
                        logger.error("❌ 토큰 파일 없음: /app/credentials/token.json")
                        logger.error("로컬에서 'python generate_token.py' 실행하여 토큰 생성 필요")
                        return None
                elif os.path.exists(creds_path):
                    logger.info("JSON 파일에서 OAuth 클라이언트 정보 로드")
                    if not os.path.exists(token_path):
                        logger.error("❌ 토큰 파일 없음")
                        logger.error("로컬에서 'python generate_token.py' 실행하여 토큰 생성 필요")
                        return None
                else:
                    logger.error("❌ Google Drive 인증 정보 없음")
                    logger.error("방법 1: .env에 DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET 설정")
                    logger.error("방법 2: credentials/google_credentials.json 파일 추가")
                    return None

        try:
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Drive 서비스 생성 실패: {e}")
            return None

    def upload(self, file_path, filename):
        """오디오 파일 업로드"""
        if not self.service:
            logger.error("구글 드라이브 서비스 없음")
            return None

        try:
            file_metadata = {
                'name': filename,
            }

            # 폴더 지정
            if self.folder_id:
                file_metadata['parents'] = [self.folder_id]

            media = MediaFileUpload(
                file_path,
                mimetype='audio/mpeg',
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

            logger.info(f"✅ 업로드 완료: {filename} (ID: {file.get('id')})")
            return file.get('id')

        except Exception as e:
            logger.error(f"❌ 업로드 실패: {e}")
            return None

    def upload_text(self, file_path, filename):
        """텍스트 파일 업로드"""
        if not self.service:
            logger.error("구글 드라이브 서비스 없음")
            return None

        try:
            file_metadata = {
                'name': filename,
            }

            # 폴더 지정
            if self.folder_id:
                file_metadata['parents'] = [self.folder_id]

            media = MediaFileUpload(
                file_path,
                mimetype='text/plain; charset=utf-8',
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

            logger.info(f"✅ 텍스트 업로드 완료: {filename} (ID: {file.get('id')})")
            return file.get('id')

        except Exception as e:
            logger.error(f"❌ 텍스트 업로드 실패: {e}")
            return None
