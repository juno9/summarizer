"""
유튜브 채널 모니터링
"""
import yt_dlp
import logging
from datetime import datetime
from models import Database, Channel

logger = logging.getLogger(__name__)


class YouTubeMonitor:
    def __init__(self, config=None):
        self.config = config
        self.db = Database()

        # 환경변수 채널 + DB 채널 모두 사용
        self.env_channels = config.youtube_channels if config else []

        logger.info(f"모니터 초기화: 환경변수 채널 {len(self.env_channels)}개")

    def get_all_channels(self):
        """모든 활성 채널 URL 가져오기"""
        channels = set(self.env_channels)

        # DB에서 활성 채널 추가
        db_channels = self.db.get_channels(active_only=True)
        for ch in db_channels:
            channels.add(ch.channel_url)

        return list(channels)

    def check_new_videos(self):
        """모든 채널의 새 영상 체크"""
        new_videos = []
        channels = self.get_all_channels()

        logger.info(f"총 {len(channels)}개 채널 체크 시작")

        for channel_url in channels:
            logger.info(f"채널 체크: {channel_url}")
            videos = self._get_recent_videos(channel_url)

            for video in videos:
                if not self._is_processed(video['id']):
                    new_videos.append(video)
                    logger.info(f"  → 새 영상: {video['title']}")

            # 채널 last_checked 업데이트
            self._update_channel_checked(channel_url)

        return new_videos

    def _get_recent_videos(self, channel_url):
        """채널의 최근 영상 가져오기"""
        # 채널 URL에 /videos 추가하여 실제 동영상 목록 가져오기
        videos_url = channel_url.rstrip('/') + '/videos'

        ydl_opts = {
            'quiet': True,
            'extract_flat': 'in_playlist',
            'playlistend': 5,  # 최근 5개만
            'ignoreerrors': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(videos_url, download=False)

                if not info or 'entries' not in info:
                    logger.warning(f"채널 정보 없음: {channel_url}")
                    return []

                videos = []
                for entry in info['entries']:
                    if entry and entry.get('id'):
                        # 실제 비디오 ID인지 확인 (UC로 시작하면 채널 ID)
                        video_id = entry['id']
                        if video_id.startswith('UC'):
                            continue
                        videos.append({
                            'id': video_id,
                            'title': entry.get('title', 'Unknown'),
                            'url': f"https://www.youtube.com/watch?v={video_id}",
                            'channel': info.get('channel', info.get('uploader', 'Unknown'))
                        })
                return videos

        except Exception as e:
            logger.error(f"채널 체크 실패 {channel_url}: {e}")
            return []

    def _is_processed(self, video_id):
        """영상 처리 여부 확인"""
        return self.db.is_video_processed(video_id)

    def mark_processed(self, video_id, title, channel, summary=None, audio_file_id=None, status='completed'):
        """영상을 처리됨으로 표시"""
        self.db.add_processed_video(
            video_id=video_id,
            title=title,
            channel=channel,
            summary=summary,
            audio_file_id=audio_file_id,
            status=status
        )
        logger.info(f"영상 처리 완료 기록: {title}")

    def _update_channel_checked(self, channel_url):
        """채널의 last_checked 업데이트"""
        session = self.db.get_session()
        channel = session.query(Channel).filter_by(channel_url=channel_url).first()
        if channel:
            channel.last_checked = datetime.now()
            session.commit()
