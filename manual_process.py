#!/usr/bin/env python3
"""
YouTube 영상 수동 처리 스크립트
루트 디렉토리에서 실행: python manual_process.py <YouTube_URL>
"""
import os
import sys

# app 디렉토리를 sys.path에 추가 (app 내부 모듈 import 해결)
APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app')
sys.path.insert(0, APP_DIR)

from dotenv import load_dotenv
load_dotenv()

from processor import SimpleProcessor
from config import Config


def manual_process(video_url):
    """특정 영상 수동 처리"""
    try:
        cfg = Config()
        proc = SimpleProcessor(cfg)

        print(f"[시작] 영상 처리 시작: {video_url}")

        # 비디오 ID 추출
        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'extract_flat': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            video_id = info['id']
            title = info.get('title', 'Unknown')
            channel = info.get('uploader', 'Unknown')

            video = {
                'id': video_id,
                'title': title,
                'url': video_url,
                'channel': channel
            }

            print(f"[제목] {title}")
            print(f"[채널] {channel}")
            print(f"[ID] {video_id}")

            # 처리 시작
            success = proc.process_video(video)

            if success:
                print("[완료] 영상 처리 완료!")
                print("[결과] 결과 파일: data/youtube_summarizer.db")
            else:
                print("[실패] 영상 처리 실패!")

    except Exception as e:
        print(f"[에러] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python manual_process.py <YouTube_URL>")
        print("예시: python manual_process.py https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        sys.exit(1)

    video_url = sys.argv[1]
    manual_process(video_url)
