#!/bin/bash

echo "호스트 환경 설정..."

# CUDA 확인
nvidia-smi

# Python 패키지 설치
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip3 install openai-whisper

# Coqui TTS (선택사항)
read -p "Coqui TTS 설치? (품질 좋지만 느림) [y/N]: " response
if [[ "$response" =~ ^[Yy]$ ]]; then
    pip3 install TTS
fi

echo "✅ 설정 완료!"