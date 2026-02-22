"""
Drive 미업로드 영상 재업로드 스크립트
- DB에 요약은 있지만 Drive에 안 올라간 영상들을 재업로드
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from dotenv import load_dotenv
load_dotenv()

from models import Database, ProcessedVideo
from uploader import GoogleDriveUploader

class SimpleConfig:
    def __init__(self):
        self.google_drive_folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID', '')

def main():
    config = SimpleConfig()
    uploader = GoogleDriveUploader(config)

    if not uploader.service:
        print("[오류] Google Drive 서비스 초기화 실패. 토큰을 확인하세요.")
        return

    db = Database()
    videos = db.session.query(ProcessedVideo).filter(
        ProcessedVideo.status == 'completed',
        ProcessedVideo.summary.isnot(None),
        (ProcessedVideo.audio_file_id.is_(None)) | (ProcessedVideo.audio_file_id == '')
    ).all()

    print(f"Drive 미업로드 영상: {len(videos)}개\n")

    if not videos:
        print("재업로드할 영상이 없습니다.")
        return

    temp_dir = os.path.join(tempfile.gettempdir(), "youtube_temp")
    os.makedirs(temp_dir, exist_ok=True)

    success = 0
    fail = 0

    for v in videos:
        print(f"업로드 중: {v.title[:60]}...", end=" ")

        # 임시 파일 생성
        summary_file = os.path.join(temp_dir, f"{v.video_id}_summary.txt")
        content = f"""================================================================================
YouTube 영상 요약
================================================================================

제목: {v.title}
영상 ID: {v.video_id}
URL: https://www.youtube.com/watch?v={v.video_id}

--------------------------------------------------------------------------------
요약
--------------------------------------------------------------------------------
{v.summary}

================================================================================
"""
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(content)

        # 업로드
        safe_title = "".join(c for c in v.title if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
        file_id = uploader.upload_text(summary_file, f"{safe_title}_요약.txt")

        # 임시 파일 삭제
        try:
            os.remove(summary_file)
        except:
            pass

        if file_id:
            v.audio_file_id = file_id
            db.session.commit()
            print(f"OK ({file_id})")
            success += 1
        else:
            print("FAIL")
            fail += 1

    print(f"\n완료: 성공 {success}개, 실패 {fail}개")

if __name__ == '__main__':
    main()
