"""
유튜브 채널 모니터링 - Rate Limit 최적화
"""
import logging
import time
import random
from datetime import datetime, timedelta
import re
from models import Database, Channel

logger = logging.getLogger(__name__)

class RateLimitManager:
    """YouTube Rate Limit 관리자"""
    
    def __init__(self):
        self.last_request_time = {}
        self.min_interval = 2  # 최소 요청 간격 (초)
        self.max_retries = 3
        self.base_delay = 5  # 기본 지연 시간 (초)
    
    def wait_before_request(self, endpoint="default"):
        """요청 전 대기"""
        now = time.time()
        
        if endpoint in self.last_request_time:
            elapsed = now - self.last_request_time[endpoint]
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed + random.uniform(0.5, 2.0)
                logger.info(f"Rate limit 방지: {wait_time:.1f}초 대기...")
                time.sleep(wait_time)
        
        self.last_request_time[endpoint] = time.time()
    
    def handle_rate_limit(self, attempt):
        """Rate limit 발생 시 처리"""
        if attempt >= self.max_retries:
            return False
        
        # 지수 백오프
        delay = self.base_delay * (2 ** attempt) + random.uniform(1, 5)
        logger.warning(f"Rate limit 발생! {delay:.1f}초 대기 (시도 {attempt + 1}/{self.max_retries})")
        time.sleep(delay)
        
        return True

# 전역 Rate Limit 관리자
rate_manager = RateLimitManager()

class YouTubeMonitor:
    """YouTube 채널 모니터링"""

    def __init__(self, config):
        self.config = config
        self.db = Database()
        
    def get_all_channels(self):
        """모든 채널 가져오기"""
        return self.db.get_channels(active_only=True)
    
    def check_new_videos(self):
        """새 영상 체크"""
        new_videos = []
        channels = self.get_all_channels()
        
        logger.info(f"총 {len(channels)}개 채널 체크 시작")
        
        for channel in channels:
            channel_url = channel.channel_url
            videos = self._get_recent_videos(channel_url)
            
            for video in videos:
                if not self._is_processed(video['id']):
                    new_videos.append(video)
                    logger.info(f"  → 새 영상: {video['title']}")

            # 채널 last_checked 업데이트
            self._update_channel_checked(channel_url)

        return new_videos

    def _get_recent_videos(self, channel_url):
        """채널의 최근 영상 가져오기 - Rate limit 최적화"""
        # Rate limit 대기
        rate_manager.wait_before_request("channel_videos")
        
        # 채널 URL에 /videos 추가하여 실제 동영상 목록 가져오기
        videos_url = channel_url.rstrip('/') + '/videos'

        ydl_opts = {
            'quiet': True,
            'extract_flat': 'in_playlist',
            'playlistend': 3,  # 최근 3개만으로 제한 (rate limit 방지)
            'ignoreerrors': True,
            # Rate limit 방지 설정
            'retries': 3,
            'fragment_retries': 3,
            'socket_timeout': 60,
        }
        
        try:
            logger.info(f"채널 체크: {channel_url}")
            
            import yt_dlp
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

    def mark_processed(self, video_id, title, channel, summary=None, audio_file_id=None, status='completed', error_message=None):
        """영상을 처리됨으로 표시"""
        self.db.add_processed_video(
            video_id=video_id,
            title=title,
            channel=channel,
            summary=summary,
            audio_file_id=audio_file_id,
            status=status,
            error_message=error_message
        )
        if status == 'completed':
            logger.info(f"영상 처리 완료 기록: {title}")
        else:
            logger.error(f"영상 처리 실패 기록: {title} - {error_message}")

    def _update_channel_checked(self, channel_url):
        """채널의 last_checked 업데이트"""
        session = self.db.get_session()
        channel = session.query(Channel).filter_by(channel_url=channel_url).first()
        if channel:
            channel.last_checked = datetime.now()
            session.commit()