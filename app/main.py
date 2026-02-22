#!/usr/bin/env python3
"""
메인 실행 스크립트
- 백그라운드 워커 (스케줄러)
- Flask 웹 서버
"""
import os
import sys
import logging
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# 프로젝트 루트 기준 data 디렉토리
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, 'data')
os.makedirs(_DATA_DIR, exist_ok=True)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(_DATA_DIR, 'app.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_worker():
    """백그라운드 워커 실행"""
    from youtube_monitor import YouTubeMonitor
    from processor import SimpleProcessor
    from config import Config

    try:
        config = Config()
    except ValueError as e:
        logger.warning(f"Config 로드 실패: {e}")
        logger.info("채널 설정 없이 웹 서버만 실행합니다.")
        return None

    monitor = YouTubeMonitor(config)
    processor = SimpleProcessor(config)

    def check_and_process():
        """새 영상 체크 및 처리"""
        try:
            logger.info("=== 새 영상 체크 시작 ===")
            new_videos = monitor.check_new_videos()

            if new_videos:
                logger.info(f"{len(new_videos)}개의 새 영상 발견")
                for i, video in enumerate(new_videos):
                    logger.info(f"처리 대상: {video['title']}")
                    try:
                        processor.process_video(video)
                    except Exception as e:
                        logger.error(f"영상 처리 실패: {video['title']} - {e}")

                    # YouTube rate limit 방지: 영상 간 2분 대기
                    if i < len(new_videos) - 1:
                        import time
                        logger.info("다음 영상까지 2분 대기 (rate limit 방지)...")
                        time.sleep(120)
            else:
                logger.info("새 영상 없음")

        except Exception as e:
            logger.error(f"처리 중 에러: {e}", exc_info=True)

    # 스케줄러 설정
    scheduler = BackgroundScheduler()

    # 체크 주기
    check_interval = int(os.getenv('CHECK_INTERVAL_HOURS', '1'))

    scheduler.add_job(
        check_and_process,
        'interval',
        hours=check_interval,
        id='youtube_check'
    )

    logger.info(f"스케줄러 시작 (체크 주기: {check_interval}시간)")
    logger.info(f"모니터링 채널: {len(monitor.get_all_channels())}개")

    # 시작 시 즉시 한 번 실행
    scheduler.add_job(check_and_process, id='initial_check')

    scheduler.start()
    return scheduler


def run_web():
    """Flask 웹 서버 실행"""
    from web import app

    host = os.getenv('WEB_HOST', '0.0.0.0')
    port = int(os.getenv('WEB_PORT', '5000'))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'

    logger.info(f"웹 서버 시작: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)


def main():
    """메인 실행 함수"""
    load_dotenv()

    mode = os.getenv('RUN_MODE', 'all').lower()

    if mode == 'worker':
        # 워커만 실행
        logger.info("워커 모드로 시작")
        scheduler = run_worker()
        if scheduler:
            try:
                while True:
                    import time
                    time.sleep(60)
            except (KeyboardInterrupt, SystemExit):
                scheduler.shutdown()
                logger.info("워커 종료")

    elif mode == 'web':
        # 웹 서버만 실행
        logger.info("웹 서버 모드로 시작")
        run_web()

    else:
        # 둘 다 실행 (기본)
        logger.info("=== YouTube Summarizer 시작 ===")

        # 워커는 별도 스레드에서 실행
        scheduler = run_worker()

        # 웹 서버는 메인 스레드에서 실행
        try:
            run_web()
        except (KeyboardInterrupt, SystemExit):
            if scheduler:
                scheduler.shutdown()
            logger.info("서비스 종료")


if __name__ == "__main__":
    main()
