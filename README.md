# YouTube 요약봇

유튜브 채널을 모니터링하고 새 영상을 자동으로 요약하여 MP3로 변환 후 구글 드라이브에 저장합니다.

## 기능

- 유튜브 채널 자동 모니터링
- Gemini 2.0 Flash로 영상 요약
- TTS로 음성 변환
- 구글 드라이브 자동 업로드
- 웹 UI로 관리

## 설치

### 1. 환경 변수 설정
```bash
cp .env.example .env
# .env 파일 편집
```

### 2. 구글 드라이브 인증

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 프로젝트 생성
3. Drive API 활성화
4. OAuth 2.0 클라이언트 ID 생성 (데스크톱 앱)
5. JSON 다운로드 → `credentials/google_credentials.json`에 저장

### 3. 실행
```bash
docker-compose up -d
```

### 4. 웹 UI 접속
```
http://localhost:5000
```

## 웹 UI 기능

- 채널 관리 (추가/삭제/활성화)
- 대시보드 (통계)
- 처리 기록
- 실시간 로그

## 로그 확인
```bash
docker-compose logs -f worker
```

## 중지
```bash
docker-compose down
```
