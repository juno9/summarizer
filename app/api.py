"""
REST API 엔드포인트
별도 Blueprint로 분리 가능
"""
import os
import re
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from models import Database

api = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)
db = Database()


def validate_youtube_url(url):
    """YouTube URL 검증"""
    patterns = [
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/@[\w-]+',
        r'youtube\.com/channel/[\w-]+',
        r'youtube\.com/c/[\w-]+',
    ]
    for pattern in patterns:
        if re.search(pattern, url):
            return True
    return False


def extract_video_id(url):
    """YouTube 비디오 ID 추출"""
    patterns = [
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


# ========== 통계 ==========
@api.route('/stats')
def get_stats():
    """시스템 통계"""
    try:
        stats = db.get_stats()
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        logger.error(f"통계 조회 실패: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ========== 채널 관리 ==========
@api.route('/channels', methods=['GET'])
def list_channels():
    """채널 목록"""
    active_only = request.args.get('active', 'false').lower() == 'true'
    channels = db.get_channels(active_only=active_only)
    return jsonify({
        'success': True,
        'count': len(channels),
        'data': [c.to_dict() for c in channels]
    })


@api.route('/channels', methods=['POST'])
def create_channel():
    """채널 추가"""
    data = request.get_json()

    if not data or 'channel_url' not in data:
        return jsonify({'success': False, 'error': 'channel_url required'}), 400

    channel_url = data['channel_url'].strip()

    if not validate_youtube_url(channel_url):
        return jsonify({'success': False, 'error': 'Invalid YouTube URL'}), 400

    channel_name = data.get('channel_name')
    channel = db.add_channel(channel_url, channel_name)

    if channel:
        db.add_log('INFO', f'API: 채널 추가 - {channel_url}', 'api')
        return jsonify({
            'success': True,
            'data': channel.to_dict()
        }), 201
    else:
        return jsonify({'success': False, 'error': 'Channel already exists'}), 409


@api.route('/channels/<int:channel_id>', methods=['DELETE'])
def remove_channel(channel_id):
    """채널 삭제"""
    if db.delete_channel(channel_id):
        db.add_log('INFO', f'API: 채널 삭제 - ID {channel_id}', 'api')
        return jsonify({'success': True, 'message': 'Channel deleted'})
    return jsonify({'success': False, 'error': 'Channel not found'}), 404


@api.route('/channels/<int:channel_id>/toggle', methods=['POST'])
def toggle_channel_api(channel_id):
    """채널 활성화/비활성화"""
    channel = db.toggle_channel(channel_id)
    if channel:
        return jsonify({
            'success': True,
            'data': channel.to_dict()
        })
    return jsonify({'success': False, 'error': 'Channel not found'}), 404


@api.route('/channels/<int:channel_id>/process-latest', methods=['POST'])
def process_latest_video(channel_id):
    """채널의 최신 영상 처리"""
    from models import Channel
    from youtube_monitor import YouTubeMonitor
    from processor import SimpleProcessor
    from config import Config

    # 채널 조회
    session = db.get_session()
    channel = session.query(Channel).filter_by(id=channel_id).first()

    if not channel:
        return jsonify({'success': False, 'error': 'Channel not found'}), 404

    try:
        # 설정 로드
        config = Config()
        monitor = YouTubeMonitor(config)

        # 최신 영상 가져오기
        videos = monitor._get_recent_videos(channel.channel_url)

        if not videos:
            return jsonify({
                'success': False,
                'error': 'No videos found in this channel'
            }), 404

        # 첫 번째 (가장 최신) 영상
        latest_video = videos[0]
        video_id = latest_video['id']

        # 이미 처리되었는지 확인
        if db.is_video_processed(video_id):
            return jsonify({
                'success': False,
                'error': 'Latest video already processed',
                'video_id': video_id,
                'title': latest_video['title']
            }), 409

        # 처리 시작
        db.add_log('INFO', f'수동 처리 시작: {latest_video["title"]}', 'api')

        processor = SimpleProcessor(config)
        processor.process_video(latest_video)

        db.add_log('INFO', f'수동 처리 완료: {latest_video["title"]}', 'api')

        return jsonify({
            'success': True,
            'message': 'Video processed successfully',
            'video_id': video_id,
            'title': latest_video['title'],
            'channel': latest_video['channel']
        })

    except Exception as e:
        logger.error(f"최신 영상 처리 실패: {e}", exc_info=True)
        db.add_log('ERROR', f'수동 처리 실패: {str(e)}', 'api')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========== 영상 ==========
@api.route('/videos', methods=['GET'])
def list_videos():
    """처리된 영상 목록"""
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    limit = min(limit, 100)  # 최대 100개

    videos = db.get_processed_videos(limit=limit, offset=offset)
    return jsonify({
        'success': True,
        'count': len(videos),
        'data': [v.to_dict() for v in videos]
    })


@api.route('/videos/<video_id>', methods=['GET'])
def get_video(video_id):
    """특정 영상 정보"""
    session = db.get_session()
    from models import ProcessedVideo
    video = session.query(ProcessedVideo).filter_by(video_id=video_id).first()

    if video:
        return jsonify({
            'success': True,
            'data': video.to_dict()
        })
    return jsonify({'success': False, 'error': 'Video not found'}), 404


@api.route('/videos/check', methods=['POST'])
def check_video():
    """영상 처리 여부 확인"""
    data = request.get_json()
    video_id = data.get('video_id')

    if not video_id:
        video_url = data.get('video_url')
        if video_url:
            video_id = extract_video_id(video_url)

    if not video_id:
        return jsonify({'success': False, 'error': 'video_id or video_url required'}), 400

    is_processed = db.is_video_processed(video_id)
    return jsonify({
        'success': True,
        'video_id': video_id,
        'is_processed': is_processed
    })


# ========== 처리 요청 ==========
@api.route('/process', methods=['POST'])
def request_processing():
    """영상 처리 요청"""
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    video_url = data.get('video_url')
    if not video_url:
        return jsonify({'success': False, 'error': 'video_url required'}), 400

    video_id = extract_video_id(video_url)
    if not video_id:
        return jsonify({'success': False, 'error': 'Invalid YouTube video URL'}), 400

    # 이미 처리되었는지 확인
    if db.is_video_processed(video_id):
        return jsonify({
            'success': False,
            'error': 'Video already processed',
            'video_id': video_id
        }), 409

    # TODO: 큐에 추가
    db.add_log('INFO', f'API: 처리 요청 - {video_url}', 'api')

    return jsonify({
        'success': True,
        'message': 'Video queued for processing',
        'video_id': video_id
    }), 202


# ========== 로그 ==========
@api.route('/logs', methods=['GET'])
def get_logs():
    """로그 조회"""
    limit = request.args.get('limit', 100, type=int)
    level = request.args.get('level')

    limit = min(limit, 500)

    logs = db.get_logs(limit=limit, level=level)
    return jsonify({
        'success': True,
        'count': len(logs),
        'data': [log.to_dict() for log in logs]
    })


# ========== 시스템 ==========
@api.route('/health')
def health_check():
    """헬스 체크"""
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


@api.route('/config')
def get_config():
    """설정 조회 (민감 정보 제외)"""
    return jsonify({
        'success': True,
        'data': {
            'check_interval_hours': int(os.getenv('CHECK_INTERVAL_HOURS', '1')),
            'tts_method': os.getenv('TTS_METHOD', 'gtts'),
            'use_local_whisper': os.getenv('USE_LOCAL_WHISPER', 'true') == 'true',
            'has_gemini_key': bool(os.getenv('GEMINI_API_KEY')),
            'has_drive_folder': bool(os.getenv('GOOGLE_DRIVE_FOLDER_ID')),
        }
    })
