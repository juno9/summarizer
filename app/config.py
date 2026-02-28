"""
설정 관리
"""
import os


class Config:
    def __init__(self):
        # 유튜브 채널 (콤마로 구분) - 선택사항
        channels_str = os.getenv('YOUTUBE_CHANNELS', '')
        self.youtube_channels = [
            c.strip() for c in channels_str.split(',') if c.strip()
        ]

        # 구글 드라이브 폴더 ID
        self.google_drive_folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID', '')

        # Google Sheets 스프레드시트 ID
        self.spreadsheet_id = os.getenv('SPREADSHEET_ID', '')

        # 체크 주기 (시간)
        self.check_interval_hours = int(os.getenv('CHECK_INTERVAL_HOURS', '1'))

        # TTS 설정
        self.tts_method = os.getenv('TTS_METHOD', 'gtts')

        # Whisper 설정
        self.use_local_whisper = os.getenv('USE_LOCAL_WHISPER', 'true').lower() == 'true'

        # LLM 제공자 설정 (gemini 또는 openrouter)
        self.llm_provider = os.getenv('LLM_PROVIDER', 'gemini').lower()
        self.has_gemini_key = bool(os.getenv('GEMINI_API_KEY'))
        self.has_openrouter_key = bool(os.getenv('OPENROUTER_API_KEY'))
        self.openrouter_model = os.getenv('OPENROUTER_MODEL', 'google/gemma-3-27b-it:free')

    def to_dict(self):
        return {
            'youtube_channels': self.youtube_channels,
            'google_drive_folder_id': self.google_drive_folder_id,
            'check_interval_hours': self.check_interval_hours,
            'tts_method': self.tts_method,
            'use_local_whisper': self.use_local_whisper,
            'spreadsheet_id': self.spreadsheet_id,
            'has_gemini_key': self.has_gemini_key,
            'llm_provider': self.llm_provider,
            'has_openrouter_key': self.has_openrouter_key,
            'openrouter_model': self.openrouter_model
        }
