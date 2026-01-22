"""
YouTube 영상 요약 프로세서
- 자막 또는 Whisper로 텍스트 추출
- Gemini로 요약
- 텍스트 파일로 Google Drive에 저장
"""
import os
import logging
from downloader import YouTubeDownloader
from uploader import GoogleDriveUploader
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Whisper 모델 (전역으로 한 번만 로드)
_whisper_model = None

def get_whisper_model():
    """Whisper 모델 로드 (싱글톤)"""
    global _whisper_model
    if _whisper_model is None:
        import whisper
        model_name = os.getenv('WHISPER_MODEL', 'base')
        logger.info(f"Whisper 모델 로딩: {model_name}")
        _whisper_model = whisper.load_model(model_name)
        logger.info("Whisper 모델 로딩 완료")
    return _whisper_model


class SimpleProcessor:
    """YouTube 영상 요약 처리"""

    def __init__(self, config):
        self.config = config
        self.downloader = YouTubeDownloader()
        self.uploader = GoogleDriveUploader(config)

        # Gemini 설정
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')

    def process_video(self, video):
        """영상 처리 메인"""
        video_id = video['id']
        video_url = video['url']
        title = video['title']

        logger.info(f"처리 시작: {title}")

        file_id = None
        summary = None

        try:
            # 1. 텍스트 추출 (자막 또는 Whisper)
            text = self._get_transcript(video_url, video_id)

            if not text:
                logger.error("자막/음성 추출 실패")
                return False

            logger.info(f"텍스트 추출 완료: {len(text)}자")

            # 2. Gemini로 요약
            logger.info("Gemini로 요약 중...")
            summary = self.summarize(text)
            logger.info(f"요약 완료: {summary[:100]}...")

            # 3. 텍스트 파일로 저장
            summary_file = self._save_summary_file(video_id, title, summary, text)
            logger.info(f"요약 파일 생성: {summary_file}")

            # 4. 구글 드라이브 업로드
            if os.path.exists(summary_file):
                # 파일명에서 특수문자 제거
                safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
                safe_title = safe_title[:50]  # 파일명 길이 제한

                file_id = self.uploader.upload_text(
                    summary_file,
                    f"{safe_title}_요약.txt"
                )

                if file_id:
                    logger.info(f"업로드 완료: {file_id}")
                else:
                    logger.warning("Google Drive 업로드 실패 (인증 설정 확인 필요)")

            # 5. 처리 완료 기록
            from youtube_monitor import YouTubeMonitor
            monitor = YouTubeMonitor(self.config)
            monitor.mark_processed(
                video_id=video_id,
                title=title,
                channel=video['channel'],
                summary=summary,
                audio_file_id=file_id
            )

            # 6. 임시 파일 정리
            self._cleanup(video_id)

            return True

        except Exception as e:
            logger.error(f"처리 중 에러: {e}", exc_info=True)
            return False

    def _get_transcript(self, video_url, video_id):
        """자막 또는 음성 인식으로 텍스트 추출"""

        # 1. 자막 시도 (한국어/영어 자동 시도)
        subtitle_text, _ = self.downloader.download_subtitle(video_url)

        if subtitle_text:
            logger.info("자막 사용")
            return subtitle_text

        # 2. 자막 없으면 Whisper로 음성 인식
        logger.info("자막 없음, Whisper로 음성 인식 시작...")

        # 오디오 다운로드
        audio_file, _ = self.downloader.download_audio(video_url)

        if not audio_file:
            logger.error("오디오 다운로드 실패")
            return None

        logger.info(f"오디오 다운로드 완료: {audio_file}")

        # Whisper로 음성 인식
        try:
            model = get_whisper_model()

            logger.info("Whisper 음성 인식 중... (시간이 걸릴 수 있습니다)")
            result = model.transcribe(
                audio_file,
                language='ko',  # 한국어
                verbose=False
            )

            text = result['text']
            logger.info(f"Whisper 음성 인식 완료: {len(text)}자")
            return text

        except Exception as e:
            logger.error(f"Whisper 음성 인식 실패: {e}")
            return None

    def summarize(self, text: str) -> str:
        """Gemini 2.0 Flash로 요약"""

        # 텍스트가 너무 길면 자르기
        max_chars = 100000  # Gemini는 긴 컨텍스트 지원
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
            logger.warning(f"텍스트 길이 초과, {max_chars}자로 제한")

        prompt = f"""다음은 유튜브 영상의 내용입니다. 핵심 내용을 요약해주세요.

요약 가이드:
1. 영상의 주제와 핵심 메시지
2. 중요한 논점이나 인사이트
3. 결론 또는 핵심 takeaway
4. 자연스러운 한국어로 작성

내용:
{text}

요약:"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    'temperature': 0.3,
                    'top_p': 0.95,
                    'max_output_tokens': 1000,
                }
            )

            return response.text.strip()

        except Exception as e:
            logger.error(f"Gemini 요약 실패: {e}")
            return "요약 생성 중 오류가 발생했습니다."

    def _save_summary_file(self, video_id: str, title: str, summary: str, original_text: str) -> str:
        """요약을 텍스트 파일로 저장"""

        output_file = f"/tmp/youtube_temp/{video_id}_summary.txt"

        content = f"""================================================================================
YouTube 영상 요약
================================================================================

제목: {title}
영상 ID: {video_id}
URL: https://www.youtube.com/watch?v={video_id}

--------------------------------------------------------------------------------
요약
--------------------------------------------------------------------------------
{summary}

--------------------------------------------------------------------------------
원본 텍스트 (처음 3000자)
--------------------------------------------------------------------------------
{original_text[:3000]}{'...' if len(original_text) > 3000 else ''}

================================================================================
"""

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)

        return output_file

    def _cleanup(self, video_id):
        """임시 파일 정리"""
        import glob
        files = glob.glob(f"/tmp/youtube_temp/{video_id}*")
        for f in files:
            try:
                os.remove(f)
                logger.debug(f"임시 파일 삭제: {f}")
            except:
                pass
