"""
Google Sheets 업로더
요약 결과를 구글 스프레드시트에 저장
"""
import os
import logging
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets',
]

TOKEN_PATH = 'credentials/token.json'

# 시트 헤더
HEADERS = ['처리일시', '제목', '채널', '영상 URL', '썸네일', '요약']


class GoogleSheetsUploader:
    def __init__(self, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        self.service = self._get_service()
        self._ensure_header()

    def _get_service(self):
        """Sheets API 서비스 생성 (token.json 재사용)"""
        if not os.path.exists(TOKEN_PATH):
            logger.warning(f"token.json 없음 ({TOKEN_PATH}). Settings에서 Google 재연동 필요.")
            return None

        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            logger.error(f"token.json 로드 실패: {e}")
            return None

        # Sheets scope 있는지 먼저 확인 (없으면 갱신해도 소용없음)
        granted = set(creds.scopes or [])
        needed = 'https://www.googleapis.com/auth/spreadsheets'
        if needed not in granted:
            logger.warning(
                "token.json에 Sheets 권한 없음 - Settings에서 Google 연동 해제 후 재연동 필요"
            )
            return None

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(TOKEN_PATH, 'w') as f:
                        f.write(creds.to_json())
                    logger.info("Sheets 토큰 갱신 완료")
                except Exception as e:
                    logger.error(f"토큰 갱신 실패: {e}")
                    return None
            else:
                logger.warning("token.json 만료 - Settings에서 Google 재연동 필요")
                return None

        try:
            return build('sheets', 'v4', credentials=creds)
        except Exception as e:
            logger.error(f"Sheets 서비스 생성 실패: {e}")
            return None

    def _ensure_header(self):
        """시트 첫 행이 비어있으면 헤더 추가"""
        if not self.service:
            return
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='A1:F1'
            ).execute()
            values = result.get('values', [])
            if not values:
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range='A1:F1',
                    valueInputOption='USER_ENTERED',
                    body={'values': [HEADERS]}
                ).execute()
                logger.info("Sheets 헤더 추가 완료")
        except Exception as e:
            logger.warning(f"헤더 확인 실패 (무시): {e}")

    def append_summary(self, video_id: str, title: str, channel: str,
                       video_url: str, summary: str, processed_at: datetime = None) -> bool:
        """요약 한 행 추가"""
        if not self.service:
            logger.error("Sheets 서비스 없음 - Settings에서 Google 재연동 필요")
            return False

        thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        dt_str = (processed_at or datetime.now()).strftime('%Y-%m-%d %H:%M')

        row = [dt_str, title, channel, video_url, thumbnail_url, summary or '']

        try:
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range='A:F',
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            logger.info(f"Sheets 저장 완료: {title}")
            return True
        except Exception as e:
            logger.error(f"Sheets 저장 실패: {e}")
            return False
