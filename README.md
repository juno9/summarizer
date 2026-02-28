# YouTube Summarizer

유튜브 채널을 자동 모니터링하고 새 영상을 AI로 요약하여 Google Sheets에 저장하는 서비스입니다.

## 주요 기능

- 유튜브 채널 자동 모니터링 (스케줄러)
- 자막 우선 추출 → 없으면 Whisper(GPU) 음성 인식
- AI 요약 (OpenRouter 무료 모델 또는 Gemini)
- 요약 결과를 **Google Sheets**에 자동 저장 (제목 / 채널 / URL / 썸네일 / 요약)
- 웹 대시보드 (채널 관리, 히스토리, 수동 처리)
- Google 계정 로그인 및 구독 채널 자동 임포트

## 요구사항

- Python 3.10 이상
- NVIDIA GPU (선택사항 - Whisper 음성 인식 가속용, CPU도 동작)
- Google Cloud Console 프로젝트

---

## 설치 방법

### 1. 저장소 클론

```bash
git clone https://github.com/your-username/youtube-summarizer.git
cd youtube-summarizer
```

### 2. 가상환경 및 패키지 설치

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

GPU 가속 Whisper를 사용하려면 (NVIDIA GPU 필요):
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install faster-whisper
```

### 3. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열고 아래 항목을 채워주세요:

| 항목 | 설명 | 필수 |
|------|------|------|
| `LLM_PROVIDER` | `openrouter` 또는 `gemini` | ✅ |
| `OPENROUTER_API_KEY` | OpenRouter API 키 | LLM_PROVIDER=openrouter 시 |
| `OPENROUTER_MODEL` | 사용할 모델 (기본: `stepfun/step-3.5-flash:free`) | |
| `GEMINI_API_KEY` | Gemini API 키 | LLM_PROVIDER=gemini 시 |
| `SPREADSHEET_ID` | Google Sheets ID | ✅ |
| `FLASK_SECRET_KEY` | 랜덤 문자열 (세션 암호화) | ✅ |

### 4. Google Cloud Console 설정

Google Sheets 저장 및 로그인 기능을 위해 한 번만 설정합니다.

#### 4-1. 프로젝트 및 API 활성화

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성
3. 아래 API 3개 활성화 (`APIs & Services → Library`):
   - **Google Sheets API**
   - **Google Drive API**
   - **YouTube Data API v3** (구독 채널 임포트 시 필요)

#### 4-2. OAuth 동의 화면 설정

1. `APIs & Services → OAuth consent screen`
2. User Type: **External**
3. 앱 이름, 이메일 입력
4. 본인 이메일을 **Test user**로 추가

#### 4-3. OAuth 클라이언트 ID 생성

1. `APIs & Services → Credentials → Create Credentials → OAuth client ID`
2. Application type: **Web application**
3. Authorized redirect URIs에 추가:
   ```
   http://localhost:5000/oauth/callback
   http://localhost:5000/auth/callback
   ```
4. 생성 후 JSON 다운로드 → `credentials/google_credentials.json`으로 저장

### 5. Google Sheets 준비

1. [Google Sheets](https://sheets.google.com)에서 새 스프레드시트 생성
2. URL에서 ID 복사:
   ```
   https://docs.google.com/spreadsheets/d/[여기가 SPREADSHEET_ID]/edit
   ```
3. `.env`의 `SPREADSHEET_ID`에 붙여넣기

### 6. 실행

```bash
# Windows
run.bat

# 직접 실행
python app/main.py
```

웹 UI 접속: http://localhost:5000

### 7. Google 계정 연동 (최초 1회)

1. 웹 UI에서 Google 로그인
2. **Settings → Google 계정 연동** 클릭
3. Drive + Sheets 권한 모두 허용

연동 후 영상 처리 시 Google Sheets에 자동 저장됩니다.

---

## LLM 설정 가이드

### OpenRouter (무료, 권장)

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=stepfun/step-3.5-flash:free
```

무료 모델 목록: https://openrouter.ai/models?q=free

추천 무료 모델:
| 모델 | 특징 |
|------|------|
| `stepfun/step-3.5-flash:free` | 빠름 (7초), 안정적 |
| `upstage/solar-pro-3:free` | 한국어 특화 |
| `meta-llama/llama-3.3-70b-instruct:free` | 고성능 (트래픽 많을 때 rate limit 가능) |

> 무료 모델은 upstream rate limit이 걸릴 수 있습니다. 재시도 로직이 내장되어 있어 자동으로 처리됩니다.

### Gemini

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIza...
```

API 키 발급: https://aistudio.google.com/app/apikey (Free Tier 제공)

---

## Google Sheets 저장 형식

| A: 처리일시 | B: 제목 | C: 채널 | D: 영상 URL | E: 썸네일 URL | F: 요약 |
|------------|--------|--------|-----------|-------------|--------|

---

## Docker로 실행

```bash
# GPU 버전
docker-compose -f docker-compose.gpu.yml up -d

# CPU 버전
docker-compose up -d
```

---

## 디렉토리 구조

```
youtube-summarizer/
├── app/
│   ├── main.py              # 진입점 (스케줄러 + 웹서버)
│   ├── processor.py         # 영상 처리 (자막→요약→Sheets 저장)
│   ├── sheets_uploader.py   # Google Sheets 업로더
│   ├── youtube_monitor.py   # 채널 모니터링
│   ├── downloader.py        # 자막/오디오 다운로드
│   ├── whisper_gpu.py       # GPU 가속 음성 인식
│   ├── web.py               # Flask 웹 서버
│   └── templates/           # HTML 템플릿
├── credentials/             # 인증 파일 (git 제외)
│   └── google_credentials.json
├── data/                    # DB, 로그 (git 제외)
├── .env                     # 환경 변수 (git 제외)
├── .env.example             # 환경 변수 예시
└── requirements.txt
```

---

## 문제 해결

**`No module named 'openai'`**
```bash
venv\Scripts\pip install openai
```

**Sheets 저장 안 됨**
- Google Cloud Console에서 **Google Sheets API** 활성화 확인
- Settings에서 Google 연동 해제 후 재연동 (Sheets 권한 포함)

**Whisper 느림**
- GPU 드라이버 및 CUDA 설치 확인
- `WHISPER_MODEL=base`로 변경 (더 빠르지만 정확도 낮음)

**rate limit (429)**
- 무료 모델은 트래픽 많을 때 발생, 자동 재시도됨
- `OPENROUTER_MODEL`을 다른 무료 모델로 변경
