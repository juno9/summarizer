#!/usr/bin/env python3
"""
Whisper 음성 인식만 수행
"""
import sys
import whisper

def transcribe_audio(audio_file):
    """음성을 텍스트로 변환"""
    print(f"Whisper 로딩...", file=sys.stderr)
    
    # medium 모델 사용 (품질/속도 균형)
    model = whisper.load_model("medium")
    
    print(f"음성 인식 시작...", file=sys.stderr)
    result = model.transcribe(audio_file, language="ko")
    
    # 표준 출력으로 텍스트만 반환
    print(result["text"])

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("사용법: python process_whisper.py <audio_file>", file=sys.stderr)
        sys.exit(1)
    
    audio_file = sys.argv[1]
    transcribe_audio(audio_file)