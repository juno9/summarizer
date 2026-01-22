"""
유튜브 영상/자막 다운로드
"""
import yt_dlp
import logging
import os

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    def __init__(self, temp_dir='/tmp/youtube_temp'):
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)
    
    def download_subtitle(self, video_url):
        """자막 다운로드"""
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['ko', 'en'],
            'subtitlesformat': 'srt',
            'outtmpl': f'{self.temp_dir}/%(id)s.%(ext)s',
            'quiet': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_id = info['id']
                
                # 한국어 자막 찾기
                subtitle_file = f"{self.temp_dir}/{video_id}.ko.srt"
                if os.path.exists(subtitle_file):
                    logger.info("한국어 자막 발견")
                    with open(subtitle_file, 'r', encoding='utf-8') as f:
                        return self._parse_srt(f.read()), video_id
                
                # 영어 자막 시도
                subtitle_file = f"{self.temp_dir}/{video_id}.en.srt"
                if os.path.exists(subtitle_file):
                    logger.info("영어 자막 발견")
                    with open(subtitle_file, 'r', encoding='utf-8') as f:
                        return self._parse_srt(f.read()), video_id
                
                logger.info("자막 없음")
                        
        except Exception as e:
            logger.error(f"자막 다운로드 실패: {e}")
        
        return None, None
    
    def download_audio(self, video_url):
        """오디오 다운로드"""
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': f'{self.temp_dir}/%(id)s.%(ext)s',
            'quiet': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_id = info['id']
                audio_file = f"{self.temp_dir}/{video_id}.mp3"
                
                if os.path.exists(audio_file):
                    logger.info(f"오디오 다운로드 완료: {audio_file}")
                    return audio_file, video_id
                    
        except Exception as e:
            logger.error(f"오디오 다운로드 실패: {e}")
        
        return None, None
    
    def _parse_srt(self, srt_content):
        """SRT 파일에서 텍스트만 추출"""
        lines = srt_content.split('\n')
        text_lines = []
        
        for line in lines:
            line = line.strip()
            # 번호나 타임코드가 아닌 실제 텍스트만
            if line and not line.isdigit() and '-->' not in line:
                text_lines.append(line)
        
        return ' '.join(text_lines)