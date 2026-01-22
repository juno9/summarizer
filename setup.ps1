# YouTube Summarizer 프로젝트 자동 설정 스크립트
# 실행: powershell -ExecutionPolicy Bypass -File setup.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "YouTube Summarizer 프로젝트 설정" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 디렉토리 구조 생성
Write-Host "📁 디렉토리 구조 생성 중..." -ForegroundColor Yellow

$dirs = @(
    "app",
    "templates",
    "static",
    "host_scripts",
    "credentials",
    "data",
    "data/cache"
)

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "  ✅ $dir" -ForegroundColor Green
    } else {
        Write-Host "  ⏭️  $dir (이미 존재)" -ForegroundColor Gray
    }
}

# 2. .gitignore 생성
Write-Host ""
Write-Host "📝 .gitignore 생성 중..." -ForegroundColor Yellow

$gitignore = @"
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
*.egg-info/

# 환경 변수
.env

# 데이터
data/*.db
data/*.log
data/cache/

# 인증
credentials/token.json
credentials/google_credentials.json

# 임시 파일
/tmp/
*.tmp
*.log

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
"@

Set-Content -Path ".gitignore" -Value $gitignore
Write-Host "  ✅ .gitignore" -ForegroundColor Green

# 3. app/models.py
Write-Host ""
Write-Host "📝 app/models.py 생성 중..." -ForegroundColor Yellow

$models = @"
"""
데이터베이스 모델
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Integer, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class Channel(Base):
    """모니터링 채널"""
    __tablename__ = 'channels'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, unique=True, nullable=False)
    enabled = Column(Boolean, default=True)
    added_at = Column(DateTime, default=datetime.now)
    last_checked = Column(DateTime, nullable=True)

class ProcessedVideo(Base):
    """처리된 영상"""
    __tablename__ = 'processed_videos'
    
    id = Column(Integer, primary_key=True)
    video_id = Column(String, unique=True, nullable=False)
    title = Column(String)
    channel = Column(String)
    channel_url = Column(String)
    processed_at = Column(DateTime, default=datetime.now)
    summary = Column(Text, nullable=True)
    audio_file_id = Column(String, nullable=True)
    status = Column(String, default='completed')

# DB 초기화
engine = create_engine('sqlite:///data/youtube_summarizer.db')
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    """DB 세션 가져오기"""
    db = SessionLocal()
    return db
"@

Set-Content -Path "app/models.py" -Value $models -Encoding UTF8
Write-Host "  ✅ app/models.py" -ForegroundColor Green

# 4. app/config.py
Write-Host ""
Write-Host "📝 app/config.py 생성 중..." -ForegroundColor Yellow

$config = @"
"""
설정 관리
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self):
        # Gemini API
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        
        # 유튜브 채널 (DB에서 관리하므로 여기선 사용 안 함)
        channels_str = os.getenv('YOUTUBE_CHANNELS', '')
        self.youtube_channels = [
            c.strip() for c in channels_str.split(',') if c.strip()
        ]
        
        # 구글 드라이브
        self.google_drive_folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID', '')
        
        # 체크 주기
        self.check_interval_hours = int(os.getenv('CHECK_INTERVAL_HOURS', '1'))
        
        # Whisper 설정
        self.use_local_whisper = os.getenv('USE_LOCAL_WHISPER', 'true').lower() == 'true'
        
        # TTS 설정
        self.tts_method = os.getenv('TTS_METHOD', 'gtts')
"@

Set-Content -Path "app/config.py" -Value $config -Encoding UTF8
Write-Host "  ✅ app/config.py" -ForegroundColor Green

# 5. .env.example
Write-Host ""
Write-Host "📝 .env.example 생성 중..." -ForegroundColor Yellow

$envExample = @"
# Gemini API 키 (https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=your_gemini_api_key_here

# 유튜브 채널 (콤마로 구분, 웹에서 관리 가능)
YOUTUBE_CHANNELS=

# 구글 드라이브 폴더 ID (선택사항)
GOOGLE_DRIVE_FOLDER_ID=

# 체크 주기 (시간)
CHECK_INTERVAL_HOURS=1

# Whisper 설정
USE_LOCAL_WHISPER=true

# TTS 방식 (gtts 또는 coqui)
TTS_METHOD=gtts
"@

Set-Content -Path ".env.example" -Value $envExample -Encoding UTF8
Write-Host "  ✅ .env.example" -ForegroundColor Green

# 6. .env 생성 (없을 경우에만)
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "  ✅ .env (템플릿 복사됨, 직접 편집 필요)" -ForegroundColor Green
} else {
    Write-Host "  ⏭️  .env (이미 존재)" -ForegroundColor Gray
}

# 7. requirements.txt
Write-Host ""
Write-Host "📝 requirements.txt 생성 중..." -ForegroundColor Yellow

$requirements = @"
yt-dlp==2023.12.30
google-api-python-client==2.110.0
google-auth-httplib2==0.2.0
google-auth-oauthlib==1.2.0
apscheduler==3.10.4
python-dotenv==1.0.0
sqlalchemy==2.0.23
google-generativeai==0.3.2
gTTS==2.5.0
flask==3.0.0
"@

Set-Content -Path "requirements.txt" -Value $requirements -Encoding UTF8
Write-Host "  ✅ requirements.txt" -ForegroundColor Green

# 8. Dockerfile
Write-Host ""
Write-Host "📝 Dockerfile 생성 중..." -ForegroundColor Yellow

$dockerfile = @"
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/
COPY templates/ /app/templates/
COPY static/ /app/static/

RUN mkdir -p /tmp/youtube_temp /app/data /app/credentials

CMD ["python", "main.py"]
"@

Set-Content -Path "Dockerfile" -Value $dockerfile -Encoding UTF8
Write-Host "  ✅ Dockerfile" -ForegroundColor Green

# 9. docker-compose.yml
Write-Host ""
Write-Host "📝 docker-compose.yml 생성 중..." -ForegroundColor Yellow

$dockerCompose = @"
version: '3.8'

services:
  worker:
    build: .
    container_name: youtube_worker
    restart: unless-stopped
    command: python main.py
    volumes:
      - ./data:/app/data
      - ./.env:/app/.env
      - ./credentials:/app/credentials
      - ./host_scripts:/host_scripts
      - /tmp/youtube_temp:/tmp/youtube_temp
    environment:
      - TZ=Asia/Seoul
    network_mode: host

  web:
    build: .
    container_name: youtube_web
    restart: unless-stopped
    command: python web.py
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
      - ./.env:/app/.env
      - ./templates:/app/templates
      - ./static:/app/static
    environment:
      - TZ=Asia/Seoul
    depends_on:
      - worker
"@

Set-Content -Path "docker-compose.yml" -Value $dockerCompose -Encoding UTF8
Write-Host "  ✅ docker-compose.yml" -ForegroundColor Green

# 10. README.md
Write-Host ""
Write-Host "📝 README.md 생성 중..." -ForegroundColor Yellow

$readme = @"
# YouTube 요약봇

유튜브 채널을 모니터링하고 새 영상을 자동으로 요약하여 MP3로 변환 후 구글 드라이브에 저장합니다.

## 기능

- 🎥 유튜브 채널 자동 모니터링
- 📝 Gemini 2.0 Flash로 영상 요약
- 🔊 TTS로 음성 변환
- ☁️  구글 드라이브 자동 업로드
- 🌐 웹 UI로 관리

## 설치

### 1. 환경 변수 설정
``````bash
cp .env.example .env
# .env 파일 편집
``````

### 2. 구글 드라이브 인증

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 프로젝트 생성
3. Drive API 활성화
4. OAuth 2.0 클라이언트 ID 생성 (데스크톱 앱)
5. JSON 다운로드 → `credentials/google_credentials.json`에 저장

### 3. 실행
``````bash
docker-compose up -d
``````

### 4. 웹 UI 접속
``````
http://localhost:5000
``````

## 웹 UI 기능

- 📺 채널 관리 (추가/삭제/활성화)
- 📊 대시보드 (통계)
- 📜 처리 기록
- 📋 실시간 로그

## 로그 확인
``````bash
docker-compose logs -f worker
``````

## 중지
``````bash
docker-compose down
``````
"@

Set-Content -Path "README.md" -Value $readme -Encoding UTF8
Write-Host "  ✅ README.md" -ForegroundColor Green

# 11. host_scripts/requirements_host.txt
Write-Host ""
Write-Host "📝 host_scripts/requirements_host.txt 생성 중..." -ForegroundColor Yellow

$hostReqs = @"
openai-whisper==20231117
torch==2.1.0
TTS==0.22.0
"@

Set-Content -Path "host_scripts/requirements_host.txt" -Value $hostReqs -Encoding UTF8
Write-Host "  ✅ host_scripts/requirements_host.txt" -ForegroundColor Green

# 완료
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ 기본 파일 생성 완료!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📝 다음 단계:" -ForegroundColor Yellow
Write-Host "  1. .env 파일 편집 (GEMINI_API_KEY 입력)" -ForegroundColor White
Write-Host "  2. credentials/google_credentials.json 생성" -ForegroundColor White
Write-Host "  3. Claude Code에서 나머지 Python 파일 생성 요청" -ForegroundColor White
Write-Host "  4. docker-compose up -d" -ForegroundColor White
Write-Host ""
Write-Host "💡 Claude Code에 다음 메시지 입력:" -ForegroundColor Yellow
Write-Host '  "나머지 Python 파일들(processor.py, web.py, main.py 등) 생성해줘"' -ForegroundColor Cyan
Write-Host ""