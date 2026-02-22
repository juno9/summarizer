"""
YouTube 영상 요약 프로세서
- GPU 가속 Whisper (faster-whisper)
- Gemini API로 요약
- 텍스트 파일로 Google Drive에 저장
- 에러 분류 및 재시도 지원
"""
import os
import tempfile
import logging
import google.generativeai as genai
from downloader import YouTubeDownloader
from uploader import GoogleDriveUploader
from whisper_gpu import transcribe_with_gpu
from error_classifier import classify_error, get_failure_reason_display, is_permanent_failure

logger = logging.getLogger(__name__)

# Windows 임시 디렉토리
TEMP_DIR = os.path.join(tempfile.gettempdir(), "youtube_temp")
os.makedirs(TEMP_DIR, exist_ok=True)


class SimpleProcessor:
    """YouTube 영상 요약 처리 (GPU Whisper + Gemini API)"""

    def __init__(self, config):
        self.config = config
        self.downloader = YouTubeDownloader()
        self.uploader = GoogleDriveUploader(config)

        # Gemini API 초기화 (항상 사용)
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다")
        genai.configure(api_key=api_key)
        self.gemini_model = genai.GenerativeModel('gemini-2.0-flash')
        logger.info("Gemini API 초기화 완료")

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
            text, extract_error = self._get_transcript(video_url, video_id)

            if not text:
                error_msg = extract_error or "자막/음성 추출 실패"
                logger.error(f"자막/음성 추출 실패: {error_msg}")

                # 에러 분류
                failure_reason, is_retryable, description = classify_error(error_msg)
                logger.info(f"에러 분류: {get_failure_reason_display(failure_reason)} - {description}")

                # 실패 기록
                from youtube_monitor import YouTubeMonitor
                monitor = YouTubeMonitor(self.config)
                monitor.mark_processed(
                    video_id=video_id,
                    title=title,
                    channel=video['channel'],
                    summary=None,
                    audio_file_id=None,
                    status='failed',
                    error_message=error_msg,
                    failure_reason=failure_reason,
                    is_retryable=is_retryable
                )
                self._cleanup(video_id)
                return False

            logger.info(f"텍스트 추출 완료: {len(text)}자")

            # 2. Gemini로 요약
            logger.info("Gemini로 요약 중...")
            summary, summarize_error = self.summarize(text)

            if not summary:
                error_msg = summarize_error or "요약 생성 실패"
                logger.error(f"요약 실패: {error_msg}")

                # 에러 분류
                failure_reason, is_retryable, description = classify_error(error_msg)
                logger.info(f"에러 분류: {get_failure_reason_display(failure_reason)} - {description}")

                # 실패 기록
                from youtube_monitor import YouTubeMonitor
                monitor = YouTubeMonitor(self.config)
                monitor.mark_processed(
                    video_id=video_id,
                    title=title,
                    channel=video['channel'],
                    summary=None,
                    audio_file_id=None,
                    status='failed',
                    error_message=error_msg,
                    failure_reason=failure_reason,
                    is_retryable=is_retryable
                )
                self._cleanup(video_id)
                return False

            logger.info(f"요약 완료: {summary[:100]}...")

            # 3. 텍스트 파일로 저장
            summary_file = self._save_summary_file(video_id, title, summary)
            logger.info(f"요약 파일 생성: {summary_file}")

            # 4. 구글 드라이브 업로드
            if os.path.exists(summary_file):
                safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
                safe_title = safe_title[:50]

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
            error_msg = str(e)
            logger.error(f"처리 중 에러: {error_msg}", exc_info=True)

            # 에러 분류
            failure_reason, is_retryable, description = classify_error(error_msg)
            logger.info(f"에러 분류: {get_failure_reason_display(failure_reason)} - {description}")

            # 실패 기록 저장
            from youtube_monitor import YouTubeMonitor
            monitor = YouTubeMonitor(self.config)
            monitor.mark_processed(
                video_id=video_id,
                title=title,
                channel=video['channel'],
                summary=None,
                audio_file_id=None,
                status='failed',
                error_message=error_msg,
                failure_reason=failure_reason,
                is_retryable=is_retryable
            )
            self._cleanup(video_id)
            return False

    def _get_transcript(self, video_url, video_id):
        """자막 또는 GPU 가속 음성 인식으로 텍스트 추출

        Returns:
            tuple: (text, error_message) - 성공 시 (text, None), 실패 시 (None, error_message)
        """
        # 1. 자막 시도 (한국어/영어 자동 시도)
        try:
            subtitle_text, _ = self.downloader.download_subtitle(video_url)

            if subtitle_text:
                logger.info("자막 사용")
                return subtitle_text, None
        except Exception as e:
            error_msg = str(e)
            logger.error(f"자막 다운로드 실패: {error_msg}")
            # 멤버십 등 접근 불가 에러면 바로 반환
            if any(keyword in error_msg.lower() for keyword in ['members-only', 'join this channel', 'private video', 'unavailable']):
                return None, error_msg

        # 2. 자막 없으면 GPU 가속 Whisper로 음성 인식
        logger.info("자막 없음, GPU 가속 Whisper로 음성 인식 시작...")

        try:
            audio_file, _ = self.downloader.download_audio(video_url)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"오디오 다운로드 실패: {error_msg}")
            return None, error_msg

        if not audio_file:
            return None, "오디오 다운로드 실패"

        logger.info(f"오디오 다운로드 완료: {audio_file}")

        try:
            text = transcribe_with_gpu(audio_file, language='ko')

            if text and len(text.strip()) > 0:
                logger.info(f"GPU Whisper 음성 인식 완료: {len(text)}자")
                return text, None
            else:
                return None, "GPU Whisper 결과가 비어있음"

        except Exception as e:
            error_msg = str(e)
            logger.error(f"GPU Whisper 음성 인식 실패: {error_msg}")
            return None, error_msg

    def summarize(self, text: str) -> tuple:
        """Gemini API로 요약 (429 에러 시 자동 재시도)

        Returns:
            tuple: (summary, error_message) - 성공 시 (summary, None), 실패 시 (None, error_message)
        """
        import time

        # 텍스트 길이 제한
        max_chars = 100000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
            logger.warning(f"텍스트 길이 초과, {max_chars}자로 제한")

        prompt = f"""다음은 유튜브 영상의 내용입니다. 핵심 내용을 요약해주세요.

요약 규칙:
- 마크다운 문법(**, ##, *, - 등) 절대 사용하지 마세요
- 순수 텍스트로만 작성하세요
- 아래 형식을 정확히 따르세요

형식:
[주제]
영상의 주제를 한 줄로 작성

[핵심 내용]
1. 첫 번째 핵심 포인트
2. 두 번째 핵심 포인트
3. 세 번째 핵심 포인트
(필요한 만큼 번호를 매겨 작성)

[결론]
영상의 결론과 핵심 takeaway를 2~3줄로 작성

내용:
{text}

요약:"""

        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = self.gemini_model.generate_content(
                    prompt,
                    generation_config={
                        'temperature': 0.3,
                        'top_p': 0.95,
                        'max_output_tokens': 1000,
                    }
                )
                return response.text.strip(), None

            except Exception as e:
                error_msg = str(e)
                if '429' in error_msg and attempt < max_retries - 1:
                    wait_time = 60 * (attempt + 1)
                    logger.warning(f"Rate limit 도달, {wait_time}초 대기 후 재시도 ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Gemini 요약 실패: {error_msg}")
                return None, error_msg

    def _save_summary_file(self, video_id: str, title: str, summary: str) -> str:
        """요약을 텍스트 파일로 저장"""

        output_file = os.path.join(TEMP_DIR, f"{video_id}_summary.txt")

        content = f"""========================================
  YouTube 영상 요약
========================================

  제목 : {title}
  URL  : https://www.youtube.com/watch?v={video_id}

----------------------------------------

{summary}

========================================
"""

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)

        return output_file

    def _cleanup(self, video_id):
        """임시 파일 정리"""
        import glob
        files = glob.glob(os.path.join(TEMP_DIR, f"{video_id}*"))
        for f in files:
            try:
                os.remove(f)
                logger.debug(f"임시 파일 삭제: {f}")
            except:
                pass

    def retry_failed_video(self, video_id: str) -> dict:
        """
        실패한 영상 재시도

        Returns:
            dict: {'success': bool, 'message': str, 'failure_reason': str}
        """
        from models import Database

        db = Database()

        # 기존 레코드 조회
        video_record = db.session.query(
            __import__('models', fromlist=['ProcessedVideo']).ProcessedVideo
        ).filter_by(video_id=video_id).first()

        if not video_record:
            return {
                'success': False,
                'message': f'영상 기록을 찾을 수 없습니다: {video_id}',
                'failure_reason': None
            }

        if video_record.status == 'completed':
            return {
                'success': False,
                'message': '이미 처리 완료된 영상입니다',
                'failure_reason': None
            }

        if not video_record.is_retryable:
            reason_display = get_failure_reason_display(video_record.failure_reason)
            return {
                'success': False,
                'message': f'재시도 불가능한 영상입니다: {reason_display}',
                'failure_reason': video_record.failure_reason
            }

        # 재시도 횟수 체크
        max_retries = 3
        if video_record.retry_count >= max_retries:
            return {
                'success': False,
                'message': f'최대 재시도 횟수 초과 ({max_retries}회)',
                'failure_reason': video_record.failure_reason
            }

        # 재시도 카운트 증가
        video_record.retry_count += 1
        video_record.status = 'processing'
        db.session.commit()

        logger.info(f"재시도 시작 ({video_record.retry_count}회차): {video_record.title}")

        # 영상 정보 구성
        video = {
            'id': video_record.video_id,
            'url': video_record.video_url or f"https://www.youtube.com/watch?v={video_id}",
            'title': video_record.title,
            'channel': video_record.channel
        }

        # 재처리 시도
        try:
            success = self._retry_process(video, db, video_record)

            if success:
                return {
                    'success': True,
                    'message': '재시도 성공',
                    'failure_reason': None
                }
            else:
                return {
                    'success': False,
                    'message': f'재시도 실패: {video_record.error_message}',
                    'failure_reason': video_record.failure_reason
                }

        except Exception as e:
            error_msg = str(e)
            failure_reason, is_retryable, description = classify_error(error_msg)

            video_record.status = 'failed'
            video_record.error_message = error_msg
            video_record.failure_reason = failure_reason
            video_record.is_retryable = is_retryable
            db.session.commit()

            return {
                'success': False,
                'message': f'재시도 실패: {description}',
                'failure_reason': failure_reason
            }

    def _retry_process(self, video, db, video_record):
        """재시도 처리 로직"""
        video_id = video['id']
        video_url = video['url']
        title = video['title']

        try:
            # 1. 텍스트 추출
            text, extract_error = self._get_transcript(video_url, video_id)

            if not text:
                error_msg = extract_error or "자막/음성 추출 실패"
                video_record.status = 'failed'
                video_record.error_message = error_msg
                failure_reason, is_retryable, _ = classify_error(error_msg)
                video_record.failure_reason = failure_reason
                video_record.is_retryable = is_retryable
                db.session.commit()
                return False

            # 2. 요약
            summary, summarize_error = self.summarize(text)

            if not summary:
                error_msg = summarize_error or "요약 생성 실패"
                video_record.status = 'failed'
                video_record.error_message = error_msg
                failure_reason, is_retryable, _ = classify_error(error_msg)
                video_record.failure_reason = failure_reason
                video_record.is_retryable = is_retryable
                db.session.commit()
                return False

            # 3. 파일 저장
            summary_file = self._save_summary_file(video_id, title, summary)

            # 4. 업로드
            file_id = None
            if os.path.exists(summary_file):
                safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
                file_id = self.uploader.upload_text(summary_file, f"{safe_title}_요약.txt")

            # 5. 성공 기록
            video_record.status = 'completed'
            video_record.summary = summary
            video_record.audio_file_id = file_id
            video_record.error_message = None
            video_record.failure_reason = None
            video_record.is_retryable = True
            db.session.commit()

            self._cleanup(video_id)
            logger.info(f"재시도 성공: {title}")
            return True

        except Exception as e:
            error_msg = str(e)
            failure_reason, is_retryable, _ = classify_error(error_msg)

            video_record.status = 'failed'
            video_record.error_message = error_msg
            video_record.failure_reason = failure_reason
            video_record.is_retryable = is_retryable
            db.session.commit()

            self._cleanup(video_id)
            logger.error(f"재시도 실패: {title} - {error_msg}")
            return False

    def get_retryable_videos(self, max_retries: int = 3) -> list:
        """재시도 가능한 실패 영상 목록 조회"""
        from models import Database
        db = Database()
        return db.get_retryable_videos(max_retries)

    def retry_all_failed(self, max_retries: int = 3) -> dict:
        """
        재시도 가능한 모든 실패 영상 재시도

        Returns:
            dict: {'total': int, 'success': int, 'failed': int, 'skipped': int, 'results': list}
        """
        retryable = self.get_retryable_videos(max_retries)

        results = {
            'total': len(retryable),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'results': []
        }

        for video in retryable:
            result = self.retry_failed_video(video.video_id)
            results['results'].append({
                'video_id': video.video_id,
                'title': video.title,
                **result
            })

            if result['success']:
                results['success'] += 1
            elif result['failure_reason'] and is_permanent_failure(result['failure_reason']):
                results['skipped'] += 1
            else:
                results['failed'] += 1

        logger.info(f"재시도 완료: 총 {results['total']}개 중 "
                   f"성공 {results['success']}, 실패 {results['failed']}, 스킵 {results['skipped']}")

        return results
