"""
Flask 웹 서버 - 대시보드
"""
import os
import re
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from models import Database
from api import api
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# HTTPS 요구 비활성화 (개발용)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_PATH = '/app/credentials/google_credentials.json'
TOKEN_PATH = '/app/credentials/token.json'

app = Flask(__name__, template_folder='/app/templates', static_folder='/app/static')
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'youtube-summarizer-secret-key-2024')

# API Blueprint 등록
app.register_blueprint(api)

logger = logging.getLogger(__name__)

try:
    db = Database()
except Exception as e:
    logger.error(f"DB 초기화 실패: {e}")
    db = None


def extract_channel_name(channel_url):
    """채널 URL에서 채널명 추출 시도"""
    # @username 형식
    match = re.search(r'@([^/]+)', channel_url)
    if match:
        return f"@{match.group(1)}"

    # /channel/UC... 형식
    match = re.search(r'/channel/([^/]+)', channel_url)
    if match:
        return match.group(1)[:20] + '...'

    # /c/channelname 형식
    match = re.search(r'/c/([^/]+)', channel_url)
    if match:
        return match.group(1)

    return None


@app.route('/')
def index():
    """대시보드 메인"""
    if db is None:
        return render_template('index.html',
                               stats={'total_processed': 0, 'active_channels': 0, 'today_processed': 0},
                               recent_videos=[],
                               channels=[],
                               error="DB 초기화 실패")

    stats = db.get_stats()
    recent_videos = db.get_processed_videos(limit=5)
    channels = db.get_channels(active_only=True)

    return render_template('index.html',
                           stats=stats,
                           recent_videos=recent_videos,
                           channels=channels)


@app.route('/channels')
def channels():
    """채널 관리 페이지"""
    if db is None:
        return render_template('channels.html', channels=[])
    all_channels = db.get_channels()
    return render_template('channels.html', channels=all_channels)


@app.route('/channels/add', methods=['POST'])
def add_channel():
    """채널 추가"""
    if db is None:
        flash('DB 연결 실패', 'error')
        return redirect(url_for('channels'))

    channel_url = request.form.get('channel_url', '').strip()

    if not channel_url:
        flash('채널 URL을 입력해주세요.', 'error')
        return redirect(url_for('channels'))

    # URL 형식 검증
    if 'youtube.com' not in channel_url and 'youtu.be' not in channel_url:
        flash('올바른 YouTube 채널 URL이 아닙니다.', 'error')
        return redirect(url_for('channels'))

    # 채널명 추출
    channel_name = extract_channel_name(channel_url) or request.form.get('channel_name')

    channel = db.add_channel(channel_url, channel_name)

    if channel:
        flash(f'채널 "{channel_name or channel_url}"이 추가되었습니다.', 'success')
        db.add_log('INFO', f'채널 추가: {channel_url}', 'web')
    else:
        flash('이미 등록된 채널입니다.', 'warning')

    return redirect(url_for('channels'))


@app.route('/channels/<int:channel_id>/toggle', methods=['POST'])
def toggle_channel(channel_id):
    """채널 활성화/비활성화"""
    channel = db.toggle_channel(channel_id)

    if channel:
        status = '활성화' if channel.is_active else '비활성화'
        flash(f'채널이 {status}되었습니다.', 'success')
    else:
        flash('채널을 찾을 수 없습니다.', 'error')

    return redirect(url_for('channels'))


@app.route('/channels/<int:channel_id>/delete', methods=['POST'])
def delete_channel(channel_id):
    """채널 삭제"""
    if db.delete_channel(channel_id):
        flash('채널이 삭제되었습니다.', 'success')
    else:
        flash('채널을 찾을 수 없습니다.', 'error')

    return redirect(url_for('channels'))


@app.route('/history')
def history():
    """처리 기록 페이지"""
    if db is None:
        return render_template('history.html', videos=[], page=1, total_pages=1, total=0)

    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    videos = db.get_processed_videos(limit=per_page, offset=offset)
    stats = db.get_stats()

    # 페이지네이션 계산
    total = stats['total_processed']
    total_pages = (total + per_page - 1) // per_page

    return render_template('history.html',
                           videos=videos,
                           page=page,
                           total_pages=total_pages,
                           total=total)


@app.route('/logs')
def logs():
    """로그 페이지"""
    level = request.args.get('level')
    log_entries = db.get_logs(limit=200, level=level) if db else []

    # 파일 로그도 읽기
    file_logs = []
    log_file = '/app/data/app.log'
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-100:]  # 최근 100줄
                file_logs = [line.strip() for line in lines if line.strip()]
        except Exception as e:
            logger.error(f"로그 파일 읽기 실패: {e}")

    return render_template('logs.html',
                           db_logs=log_entries,
                           file_logs=file_logs,
                           current_level=level)


@app.route('/logs/clear', methods=['POST'])
def clear_logs():
    """로그 초기화"""
    try:
        # 파일 로그 초기화
        log_file = '/app/data/app.log'
        if os.path.exists(log_file):
            open(log_file, 'w').close()

        flash('로그가 초기화되었습니다.', 'success')
    except Exception as e:
        flash(f'로그 초기화 실패: {e}', 'error')

    return redirect(url_for('logs'))


# ========== 설정 페이지 ==========
@app.route('/settings')
def settings():
    """설정 페이지"""
    # Google Drive 연동 상태 확인
    google_connected = os.path.exists(TOKEN_PATH)
    google_email = None

    if google_connected:
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            if creds and creds.valid:
                service = build('oauth2', 'v2', credentials=creds)
                user_info = service.userinfo().get().execute()
                google_email = user_info.get('email')
        except Exception as e:
            logger.error(f"Google 사용자 정보 조회 실패: {e}")
            google_connected = False

    # credentials.json 존재 여부
    has_credentials_file = os.path.exists(CREDENTIALS_PATH)

    return render_template('settings.html',
                           google_connected=google_connected,
                           google_email=google_email,
                           has_credentials_file=has_credentials_file,
                           drive_folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_ID', ''),
                           check_interval=os.getenv('CHECK_INTERVAL_HOURS', '1'),
                           tts_method=os.getenv('TTS_METHOD', 'gtts'))


# ========== Google OAuth ==========
@app.route('/oauth/google')
def oauth_google():
    """Google OAuth 시작"""
    if not os.path.exists(CREDENTIALS_PATH):
        flash('google_credentials.json 파일이 없습니다. credentials 폴더에 넣어주세요.', 'error')
        return redirect(url_for('settings'))

    try:
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_PATH,
            scopes=SCOPES + ['https://www.googleapis.com/auth/userinfo.email'],
            redirect_uri=url_for('oauth_callback', _external=True)
        )

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )

        session['oauth_state'] = state
        return redirect(authorization_url)

    except Exception as e:
        logger.error(f"OAuth 시작 실패: {e}")
        flash(f'OAuth 시작 실패: {e}', 'error')
        return redirect(url_for('settings'))


@app.route('/oauth/callback')
def oauth_callback():
    """Google OAuth 콜백"""
    try:
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_PATH,
            scopes=SCOPES + ['https://www.googleapis.com/auth/userinfo.email'],
            redirect_uri=url_for('oauth_callback', _external=True)
        )

        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials

        # 토큰 저장
        with open(TOKEN_PATH, 'w') as token_file:
            token_file.write(credentials.to_json())

        # 사용자 정보 가져오기
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        email = user_info.get('email', 'Unknown')

        if db:
            db.add_log('INFO', f'Google Drive 연동 완료: {email}', 'oauth')

        flash(f'Google Drive 연동 성공! ({email})', 'success')
        return redirect(url_for('settings'))

    except Exception as e:
        logger.error(f"OAuth 콜백 실패: {e}")
        flash(f'Google Drive 연동 실패: {e}', 'error')
        return redirect(url_for('settings'))


@app.route('/oauth/disconnect', methods=['POST'])
def oauth_disconnect():
    """Google Drive 연동 해제"""
    try:
        if os.path.exists(TOKEN_PATH):
            os.remove(TOKEN_PATH)

        if db:
            db.add_log('INFO', 'Google Drive 연동 해제', 'oauth')

        flash('Google Drive 연동이 해제되었습니다.', 'success')
    except Exception as e:
        flash(f'연동 해제 실패: {e}', 'error')

    return redirect(url_for('settings'))


# API 엔드포인트 (JSON 응답)
@app.route('/api/stats')
def api_stats():
    """통계 API"""
    return jsonify(db.get_stats())


@app.route('/api/channels')
def api_channels():
    """채널 목록 API"""
    channels = db.get_channels()
    return jsonify([c.to_dict() for c in channels])


@app.route('/api/videos')
def api_videos():
    """처리된 영상 목록 API"""
    limit = request.args.get('limit', 50, type=int)
    videos = db.get_processed_videos(limit=limit)
    return jsonify([v.to_dict() for v in videos])


@app.route('/api/process', methods=['POST'])
def api_process_video():
    """수동으로 영상 처리 요청"""
    video_url = request.json.get('video_url')

    if not video_url:
        return jsonify({'error': 'video_url required'}), 400

    # TODO: 큐에 추가하거나 즉시 처리
    db.add_log('INFO', f'수동 처리 요청: {video_url}', 'api')

    return jsonify({'status': 'queued', 'video_url': video_url})


@app.template_filter('timeago')
def timeago_filter(dt):
    """상대적 시간 표시"""
    if not dt:
        return '-'

    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)

    now = datetime.now()
    diff = now - dt

    if diff.days > 30:
        return dt.strftime('%Y-%m-%d')
    elif diff.days > 0:
        return f'{diff.days}일 전'
    elif diff.seconds > 3600:
        return f'{diff.seconds // 3600}시간 전'
    elif diff.seconds > 60:
        return f'{diff.seconds // 60}분 전'
    else:
        return '방금 전'


@app.errorhandler(404)
def not_found(e):
    return f"<h1>404 - Page Not Found</h1><p><a href='/'>Go Home</a></p>", 404


@app.errorhandler(500)
def server_error(e):
    return f"<h1>500 - Server Error</h1><p>{str(e)}</p><p><a href='/'>Go Home</a></p>", 500


def run_server(host='0.0.0.0', port=5000, debug=False):
    """서버 실행"""
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_server(debug=True)
