# -*- coding: cp949 -*-
"""
최소한 YouTube 요약 스크립트
"""
import os
import sys
import requests
import time

def simple_summary(video_url):
    """최소한 요약 실행"""
    try:
        print(f"🎯 영상 처리 시작: {video_url}")
        video_url = video_url.strip()
        
        # 1. 영상 정보 추출
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = info.get('title', 'Unknown')
            channel = info.get('uploader', 'Unknown')
            print(f"📹 제목: {title.encode('utf-8', errors='ignore').decode('cp949')}")
            print(f"📺 채널: {channel}")
        channel = channel.encode('utf-8', errors='ignore').decode('cp949', errors='ignore')
        
        # 2. 간단한 요약 (Ollama 사용)
        payload = {
            "model": "llama3.2:3b",
            "prompt": f"다음 유튜브 영상의 내용을 간단하게 요약해주세요: {video_url}",
            "stream": False
        }
        
        print("🤖 로컬 LLM으로 요약 중...")
        response = requests.post(
            "http://localhost:11434/api/generate",
            json=payload,
            timeout=120
        )
        
        if response.status_code == 200:
            summary = response.json().get('response', '')
            print("✅ 요약 완료!")
            print("=" * 50)
            print(summary)
            print("=" * 50)
        else:
            print(f"❌ 요약 실패: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 에러: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python simple_summary.py <YouTube_URL>")
        print("예시: python simple_summary.py https://www.youtube.com/watch?v=VIDEO_ID")
        sys.exit(1)
    
    simple_summary(sys.argv[1])