@echo off
echo RTX 4060 Ti GPU 가속 YouTube Summarizer 설치
echo ===================================================

echo 1. Python 가상환경 생성...
python -m venv gpu_env
call gpu_env\Scripts\activate

echo 2. PyTorch GPU 설치 (CUDA 12.1)...
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

echo 3. faster-whisper GPU 설치...
pip install faster-whisper

echo 4. 나머지 의존성 설치...
pip install -r requirements.txt

echo 5. Ollama 설치 확인...
ollama --version
if %errorlevel% neq 0 (
    echo Ollama 설치 필요: https://ollama.com/download
    echo 설치 후 재시작: ollama pull llama3.2:3b
) else (
    echo 6. Llama3.2 3B 모델 다운로드 (8GB VRAM 최적화)...
    ollama pull llama3.2:3b
)

echo.
echo 설치 완료!
echo 실행: python app\main.py
echo.
echo GPU 사용량 확인: nvidia-smi
pause