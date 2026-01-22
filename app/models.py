"""
데이터베이스 모델
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

Base = declarative_base()

# DB 경로
DB_PATH = os.getenv('DB_PATH', '/app/data/youtube_summarizer.db')

# 디렉토리 생성
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


class Channel(Base):
    """모니터링 채널"""
    __tablename__ = 'channels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_url = Column(String(500), unique=True, nullable=False)
    channel_name = Column(String(200))
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime, default=datetime.now)
    last_checked = Column(DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'channel_url': self.channel_url,
            'channel_name': self.channel_name,
            'is_active': self.is_active,
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'last_checked': self.last_checked.isoformat() if self.last_checked else None
        }


class ProcessedVideo(Base):
    """처리된 영상 기록"""
    __tablename__ = 'processed_videos'

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(20), unique=True, nullable=False)
    title = Column(String(500))
    channel = Column(String(200))
    video_url = Column(String(500))
    summary = Column(Text)
    audio_file_id = Column(String(100))  # 구글 드라이브 파일 ID
    status = Column(String(50), default='completed')  # pending, processing, completed, failed
    error_message = Column(Text)
    processed_at = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'video_id': self.video_id,
            'title': self.title,
            'channel': self.channel,
            'video_url': self.video_url,
            'summary': self.summary,
            'audio_file_id': self.audio_file_id,
            'status': self.status,
            'error_message': self.error_message,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None
        }


class ProcessingQueue(Base):
    """처리 대기열"""
    __tablename__ = 'processing_queue'

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(20), unique=True, nullable=False)
    video_url = Column(String(500))
    title = Column(String(500))
    channel = Column(String(200))
    priority = Column(Integer, default=0)
    status = Column(String(50), default='pending')  # pending, processing
    added_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'video_id': self.video_id,
            'video_url': self.video_url,
            'title': self.title,
            'channel': self.channel,
            'priority': self.priority,
            'status': self.status,
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None
        }


class AppLog(Base):
    """애플리케이션 로그"""
    __tablename__ = 'app_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(20))  # INFO, WARNING, ERROR
    message = Column(Text)
    source = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'level': self.level,
            'message': self.message,
            'source': self.source,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Database:
    """데이터베이스 관리 클래스"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self._initialized = True

    def get_session(self):
        return self.session

    # Channel 관련 메서드
    def add_channel(self, channel_url, channel_name=None):
        """채널 추가"""
        existing = self.session.query(Channel).filter_by(channel_url=channel_url).first()
        if existing:
            return None

        channel = Channel(channel_url=channel_url, channel_name=channel_name)
        self.session.add(channel)
        self.session.commit()
        return channel

    def get_channels(self, active_only=False):
        """채널 목록 조회"""
        query = self.session.query(Channel)
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(Channel.added_at.desc()).all()

    def toggle_channel(self, channel_id):
        """채널 활성화/비활성화 토글"""
        channel = self.session.query(Channel).filter_by(id=channel_id).first()
        if channel:
            channel.is_active = not channel.is_active
            self.session.commit()
            return channel
        return None

    def delete_channel(self, channel_id):
        """채널 삭제"""
        channel = self.session.query(Channel).filter_by(id=channel_id).first()
        if channel:
            self.session.delete(channel)
            self.session.commit()
            return True
        return False

    # ProcessedVideo 관련 메서드
    def add_processed_video(self, video_id, title, channel, video_url=None,
                           summary=None, audio_file_id=None, status='completed'):
        """처리된 영상 추가"""
        video = ProcessedVideo(
            video_id=video_id,
            title=title,
            channel=channel,
            video_url=video_url or f"https://www.youtube.com/watch?v={video_id}",
            summary=summary,
            audio_file_id=audio_file_id,
            status=status
        )
        self.session.add(video)
        self.session.commit()
        return video

    def get_processed_videos(self, limit=50, offset=0):
        """처리된 영상 목록"""
        return self.session.query(ProcessedVideo)\
            .order_by(ProcessedVideo.processed_at.desc())\
            .offset(offset)\
            .limit(limit)\
            .all()

    def is_video_processed(self, video_id):
        """영상 처리 여부 확인"""
        return self.session.query(ProcessedVideo).filter_by(video_id=video_id).first() is not None

    def get_stats(self):
        """통계 조회"""
        total_processed = self.session.query(ProcessedVideo).count()
        total_channels = self.session.query(Channel).filter_by(is_active=True).count()
        recent_count = self.session.query(ProcessedVideo)\
            .filter(ProcessedVideo.processed_at >= datetime.now().replace(hour=0, minute=0, second=0))\
            .count()

        return {
            'total_processed': total_processed,
            'active_channels': total_channels,
            'today_processed': recent_count
        }

    # 로그 관련 메서드
    def add_log(self, level, message, source='app'):
        """로그 추가"""
        log = AppLog(level=level, message=message, source=source)
        self.session.add(log)
        self.session.commit()
        return log

    def get_logs(self, limit=100, level=None):
        """로그 조회"""
        query = self.session.query(AppLog)
        if level:
            query = query.filter_by(level=level)
        return query.order_by(AppLog.created_at.desc()).limit(limit).all()
