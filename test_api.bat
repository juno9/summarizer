@echo off
echo 🌐 웹 API 테스트
echo ================================

if "%1"=="" (
    echo 사용법: test_api.bat "YouTube_URL"
    echo 예시: test_api.bat "https://www.youtube.com/watch?v=VIDEO_ID"
    pause
    exit /b
)

echo 📡 요청 보내는 중...
curl -X POST http://127.0.0.1:5000/api/process ^
  -H "Content-Type: application/json" ^
  -d "{\"url\": \"%1\"}"

echo.
echo ✅ 테스트 완료!
echo ================================
pause