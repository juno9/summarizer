@echo off
echo 🎯 YouTube 영상 간단 요약
echo ================================

if "%1"=="" (
    echo 사용법: summarize.bat "YouTube_URL"
    echo 예시: summarize.bat "https://www.youtube.com/watch?v=VIDEO_ID"
    pause
    exit /b
)

echo 📹 영상: %1
echo.

echo 🤖 Ollama으로 요약 중...
ollama run llama3.2:3b "다음 유튜브 영상의 내용을 간단하게 요약해주세요: %1. 영상의 핵심 내용을 3-5줄로 요약해주세요."

echo.
echo ✅ 요약 완료!
echo ================================
pause