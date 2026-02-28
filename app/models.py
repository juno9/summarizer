"""
데이터베이스 모델
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

Base = declarative_base()

# DB 경로
DB_PATH = os.getenv('DB_PATH', 'data/youtube_summarizer.db')

# 디렉토리 생성
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


class User(Base):
    """사용자"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    google_id = Column(String(100), unique=True, nullable=False)
    email = Column(String(200), nullable=False)
    name = Column(String(200))
    picture = Column(String(500))
    oauth_token = Column(Text)  # JSON string of OAuth credentials (youtube.readonly)
    drive_folder_id = Column(String(500))  # 유저별 Google Drive 폴더 ID
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'picture': self.picture,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Channel(Base):
    """모니터링 채널"""
    __tablename__ = 'channels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # nullable: 기존 데이터 호환
    channel_url = Column(String(500), nullable=False)
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
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # nullable: 기존 데이터 호환
    video_id = Column(String(20), nullable=False)
    title = Column(String(500))
    channel = Column(String(200))
    video_url = Column(String(500))
    summary = Column(Text)
    thumbnail_url = Column(String(500))  # 유튜브 썸네일 URL
    audio_file_id = Column(String(100))  # 구글 드라이브 파일 ID (deprecated)
    status = Column(String(50), default='completed')  # pending, processing, completed, failed
    error_message = Column(Text)
    failure_reason = Column(String(50))  # membership, rate_limit, network, auth, unknown
    retry_count = Column(Integer, default=0)
    is_retryable = Column(Boolean, default=True)  # 재시도 가능 여부
    processed_at = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'video_id': self.video_id,
            'title': self.title,
            'channel': self.channel,
            'video_url': self.video_url,
            'summary': self.summary,
            'thumbnail_url': self.thumbnail_url,
            'audio_file_id': self.audio_file_id,
            'status': self.status,
            'error_message': self.error_message,
            'failure_reason': self.failure_reason,
            'retry_count': self.retry_count,
            'is_retryable': self.is_retryable,
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

        # 마이그레이션
        self._migrate()

    def _migrate(self):
        """기존 DB에 컬럼 추가 마이그레이션"""
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # processed_videos 컬럼 확인
        cursor.execute("PRAGMA table_info(processed_videos)")
        pv_columns = [col[1] for col in cursor.fetchall()]

        if 'failure_reason' not in pv_columns:
            cursor.execute("ALTER TABLE processed_videos ADD COLUMN failure_reason VARCHAR(50)")
        if 'retry_count' not in pv_columns:
            cursor.execute("ALTER TABLE processed_videos ADD COLUMN retry_count INTEGER DEFAULT 0")
        if 'is_retryable' not in pv_columns:
            cursor.execute("ALTER TABLE processed_videos ADD COLUMN is_retryable BOOLEAN DEFAULT 1")
        if 'user_id' not in pv_columns:
            cursor.execute("ALTER TABLE processed_videos ADD COLUMN user_id INTEGER")
        if 'thumbnail_url' not in pv_columns:
            cursor.execute("ALTER TABLE processed_videos ADD COLUMN thumbnail_url VARCHAR(500)")

        # channels 컬럼 확인
        cursor.execute("PRAGMA table_info(channels)")
        ch_columns = [col[1] for col in cursor.fetchall()]

        if 'user_id' not in ch_columns:
            cursor.execute("ALTER TABLE channels ADD COLUMN user_id INTEGER")

        # users 컬럼 확인
        cursor.execute("PRAGMA table_info(users)")
        u_columns = [col[1] for col in cursor.fetchall()]

        if 'drive_folder_id' not in u_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN drive_folder_id VARCHAR(500)")

        # processed_videos video_id unique 제약 제거 (user_id별로 같은 video_id 허용)
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='processed_videos'")
        for idx_name, idx_sql in cursor.fetchall():
            if idx_sql and 'video_id' in idx_sql and 'UNIQUE' in idx_sql.upper():
                cursor.execute(f"DROP INDEX IF EXISTS {idx_name}")

        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='processed_videos'")
        pv_row = cursor.fetchone()
        if pv_row and pv_row[0]:
            pv_lines = pv_row[0].split('\n')
            pv_has_unique = any(
                'video_id' in line.lower() and 'unique' in line.lower()
                for line in pv_lines
            )
            if pv_has_unique:
                cursor.execute("""
                    CREATE TABLE processed_videos_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER REFERENCES users(id),
                        video_id VARCHAR(20) NOT NULL,
                        title VARCHAR(500),
                        channel VARCHAR(200),
                        video_url VARCHAR(500),
                        summary TEXT,
                        audio_file_id VARCHAR(100),
                        status VARCHAR(50) DEFAULT 'completed',
                        error_message TEXT,
                        failure_reason VARCHAR(50),
                        retry_count INTEGER DEFAULT 0,
                        is_retryable BOOLEAN DEFAULT 1,
                        processed_at DATETIME
                    )
                """)
                cursor.execute("""
                    INSERT INTO processed_videos_new
                    SELECT id, user_id, video_id, title, channel, video_url, summary,
                           audio_file_id, status, error_message, failure_reason,
                           retry_count, is_retryable, processed_at
                    FROM processed_videos
                """)
                cursor.execute("DROP TABLE processed_videos")
                cursor.execute("ALTER TABLE processed_videos_new RENAME TO processed_videos")

        # channel_url unique 제약 제거 (user_id별로 같은 채널 등록 가능)
        # 기존 unique 인덱스 확인 및 제거
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='channels'")
        indexes = cursor.fetchall()
        for idx_name, idx_sql in indexes:
            if idx_sql and 'channel_url' in idx_sql and 'UNIQUE' in idx_sql.upper():
                cursor.execute(f"DROP INDEX IF EXISTS {idx_name}")

        # 테이블 정의에 인라인 UNIQUE 제약이 있는 경우 테이블 재생성으로 제거
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='channels'")
        row = cursor.fetchone()
        if row and row[0]:
            table_sql = row[0].upper()
            # channel_url 컬럼에 UNIQUE가 인라인으로 있는지 확인
            lines = row[0].split('\n')
            has_inline_unique = any(
                'channel_url' in line.lower() and 'unique' in line.lower()
                for line in lines
            )
            if has_inline_unique:
                cursor.execute("""
                    CREATE TABLE channels_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER REFERENCES users(id),
                        channel_url VARCHAR(500) NOT NULL,
                        channel_name VARCHAR(200),
                        is_active BOOLEAN DEFAULT 1,
                        added_at DATETIME,
                        last_checked DATETIME
                    )
                """)
                cursor.execute("""
                    INSERT INTO channels_new (id, user_id, channel_url, channel_name, is_active, added_at, last_checked)
                    SELECT id, user_id, channel_url, channel_name, is_active, added_at, last_checked
                    FROM channels
                """)
                cursor.execute("DROP TABLE channels")
                cursor.execute("ALTER TABLE channels_new RENAME TO channels")

        conn.commit()
        conn.close()

    def get_session(self):
        return self.session

    # User 관련 메서드
    def get_or_create_user(self, google_id, email, name=None, picture=None, oauth_token=None):
        """구글 로그인으로 유저 생성 또는 업데이트"""
        user = self.session.query(User).filter_by(google_id=google_id).first()
        if user:
            user.email = email
            user.name = name
            user.picture = picture
            user.last_login = datetime.now()
            if oauth_token:
                user.oauth_token = oauth_token
        else:
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                picture=picture,
                oauth_token=oauth_token,
            )
            self.session.add(user)
        self.session.commit()
        return user

    def get_user(self, user_id):
        """유저 조회"""
        return self.session.query(User).filter_by(id=user_id).first()

    def update_user_token(self, user_id, oauth_token):
        """유저 OAuth 토큰 업데이트"""
        user = self.session.query(User).filter_by(id=user_id).first()
        if user:
            user.oauth_token = oauth_token
            self.session.commit()

    def update_user_drive_folder(self, user_id, drive_folder_id):
        """유저별 Drive 폴더 ID 업데이트"""
        user = self.session.query(User).filter_by(id=user_id).first()
        if user:
            user.drive_folder_id = drive_folder_id
            self.session.commit()
            return True
        return False

    # Channel 관련 메서드
    def add_channel(self, channel_url, channel_name=None, user_id=None):
        """채널 추가. 이미 존재하면 None 반환, DB 오류 시 예외 발생"""
        query = self.session.query(Channel).filter_by(channel_url=channel_url)
        if user_id:
            query = query.filter_by(user_id=user_id)
        if query.first():
            return None

        try:
            channel = Channel(channel_url=channel_url, channel_name=channel_name, user_id=user_id)
            self.session.add(channel)
            self.session.commit()
            return channel
        except Exception:
            self.session.rollback()
            raise

    def get_channels(self, active_only=False, user_id=None):
        """채널 목록 조회"""
        query = self.session.query(Channel)
        if user_id:
            query = query.filter_by(user_id=user_id)
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
                           summary=None, thumbnail_url=None, audio_file_id=None,
                           status='completed', error_message=None, failure_reason=None,
                           is_retryable=True, user_id=None):
        """처리된 영상 추가"""
        try:
            video = ProcessedVideo(
                video_id=video_id,
                title=title,
                channel=channel,
                video_url=video_url or f"https://www.youtube.com/watch?v={video_id}",
                summary=summary,
                thumbnail_url=thumbnail_url or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                audio_file_id=audio_file_id,
                status=status,
                error_message=error_message,
                failure_reason=failure_reason,
                is_retryable=is_retryable,
                user_id=user_id,
            )
            self.session.add(video)
            self.session.commit()
            return video
        except Exception:
            self.session.rollback()
            raise

    def get_processed_videos(self, limit=50, offset=0, user_id=None):
        """처리된 영상 목록"""
        query = self.session.query(ProcessedVideo)
        if user_id:
            query = query.filter_by(user_id=user_id)
        return query.order_by(ProcessedVideo.processed_at.desc())\
            .offset(offset)\
            .limit(limit)\
            .all()

    def is_video_processed(self, video_id, user_id=None):
        """영상 처리 여부 확인"""
        query = self.session.query(ProcessedVideo).filter_by(video_id=video_id)
        if user_id:
            query = query.filter_by(user_id=user_id)
        return query.first() is not None

    def get_retryable_videos(self, max_retries=3):
        """재시도 가능한 실패 영상 목록"""
        return self.session.query(ProcessedVideo)\
            .filter_by(status='failed', is_retryable=True)\
            .filter(ProcessedVideo.retry_count < max_retries)\
            .order_by(ProcessedVideo.processed_at.desc())\
            .all()

    def get_failed_videos(self, include_non_retryable=False):
        """실패한 영상 목록 조회"""
        query = self.session.query(ProcessedVideo).filter_by(status='failed')
        if not include_non_retryable:
            query = query.filter_by(is_retryable=True)
        return query.order_by(ProcessedVideo.processed_at.desc()).all()

    def update_video_for_retry(self, video_id):
        """재시도를 위해 영상 상태 업데이트"""
        video = self.session.query(ProcessedVideo).filter_by(video_id=video_id).first()
        if video and video.is_retryable:
            video.retry_count += 1
            video.status = 'pending'
            self.session.commit()
            return video
        return None

    def update_video_status(self, video_id, status, error_message=None,
                           failure_reason=None, is_retryable=None, summary=None, audio_file_id=None):
        """영상 상태 업데이트"""
        video = self.session.query(ProcessedVideo).filter_by(video_id=video_id).first()
        if video:
            video.status = status
            video.processed_at = datetime.now()
            if error_message is not None:
                video.error_message = error_message
            if failure_reason is not None:
                video.failure_reason = failure_reason
            if is_retryable is not None:
                video.is_retryable = is_retryable
            if summary is not None:
                video.summary = summary
            if audio_file_id is not None:
                video.audio_file_id = audio_file_id
            self.session.commit()
            return video
        return None

    def delete_video_record(self, video_id):
        """영상 기록 삭제 (재처리를 위해)"""
        video = self.session.query(ProcessedVideo).filter_by(video_id=video_id).first()
        if video:
            self.session.delete(video)
            self.session.commit()
            return True
        return False

    def get_stats(self, user_id=None):
        """통계 조회"""
        pv_query = self.session.query(ProcessedVideo)
        ch_query = self.session.query(Channel).filter_by(is_active=True)

        if user_id:
            pv_query = pv_query.filter_by(user_id=user_id)
            ch_query = ch_query.filter_by(user_id=user_id)

        total_processed = pv_query.count()
        total_channels = ch_query.count()
        recent_count = pv_query\
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
