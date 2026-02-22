"""
Flask 웹 서버 - 대시보드
"""
import os
import re
import json
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from models import Database, ProcessedVideo
from api import api
from config import Config
from error_classifier import get_failure_reason_display, is_permanent_failure
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import jwt

# HTTPS 요구 비활성화 (개발용)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# ========== 스코프 정의 ==========
# Drive 연동용 (설정 페이지)
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.file']

# 로그인용 (구글 계정 + 유튜브 구독 읽기)
LOGIN_SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/youtube.readonly',
]

CREDENTIALS_PATH = 'credentials/google_credentials.json'
TOKEN_PATH = 'credentials/token.json'  # Drive 전용 토큰 (기존 유지)

JWT_SECRET = os.getenv('JWT_SECRET_KEY', 'youtube-summarizer-jwt-secret-2024')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRE_DAYS = 30

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'youtube-summarizer-secret-key-2024')

# API Blueprint 등록
app.register_blueprint(api)

logger = logging.getLogger(__name__)

try:
    db = Database()
except Exception as e:
    logger.error(f"DB 초기화 실패: {e}")
    db = None


# ========== 인증 헬퍼 ==========

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    user_id = session.get('user_id')
    if not user_id or not db:
        return None
    return db.get_user(user_id)


def issue_jwt(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get('user_id')
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def api_login_required(f):
    """API 엔드포인트용 JWT 인증"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # 세션 인증 우선
        if 'user_id' in session:
            return f(*args, **kwargs)
        # JWT 토큰 확인
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            user_id = verify_jwt(token)
            if user_id:
                session['user_id'] = user_id
                return f(*args, **kwargs)
        return jsonify({'error': 'Unauthorized'}), 401
    return decorated


# ========== 유틸 ==========

def extract_channel_name(channel_url):
    match = re.search(r'@([^/]+)', channel_url)
    if match:
        return f"@{match.group(1)}"
    match = re.search(r'/channel/([^/]+)', channel_url)
    if match:
        return match.group(1)[:20] + '...'
    match = re.search(r'/c/([^/]+)', channel_url)
    if match:
        return match.group(1)
    return None


# ========== 로그인/로그아웃 ==========

@app.route('/login')
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/auth/google')
def auth_google():
    """Google 로그인 OAuth 시작"""
    if not os.path.exists(CREDENTIALS_PATH):
        flash('google_credentials.json 파일이 없습니다. credentials 폴더에 넣어주세요.', 'error')
        return redirect(url_for('login'))

    try:
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_PATH,
            scopes=LOGIN_SCOPES,
            redirect_uri=url_for('auth_callback', _external=True)
        )
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        session['login_oauth_state'] = state
        return redirect(authorization_url)
    except Exception as e:
        logger.error(f"Google 로그인 OAuth 시작 실패: {e}")
        flash(f'로그인 실패: {e}', 'error')
        return redirect(url_for('login'))


@app.route('/auth/callback')
def auth_callback():
    """Google 로그인 OAuth 콜백"""
    try:
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_PATH,
            scopes=LOGIN_SCOPES,
            redirect_uri=url_for('auth_callback', _external=True)
        )
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials

        # 사용자 정보 가져오기
        oauth2_service = build('oauth2', 'v2', credentials=credentials)
        user_info = oauth2_service.userinfo().get().execute()

        google_id = user_info['id']
        email = user_info.get('email', '')
        name = user_info.get('name', '')
        picture = user_info.get('picture', '')

        # DB에 유저 저장/업데이트
        user = db.get_or_create_user(
            google_id=google_id,
            email=email,
            name=name,
            picture=picture,
            oauth_token=credentials.to_json(),
        )

        session['user_id'] = user.id
        session['user_name'] = name
        session['user_picture'] = picture
        session['user_email'] = email

        if db:
            db.add_log('INFO', f'로그인: {email}', 'auth')

        flash(f'환영합니다, {name}!', 'success')
        return redirect(url_for('index'))

    except Exception as e:
        logger.error(f"Google 로그인 콜백 실패: {e}")
        flash(f'로그인 실패: {e}', 'error')
        return redirect(url_for('login'))


@app.route('/logout', methods=['POST'])
def logout():
    user_email = session.get('user_email', '')
    session.clear()
    if db and user_email:
        db.add_log('INFO', f'로그아웃: {user_email}', 'auth')
    return redirect(url_for('login'))


# ========== JWT 토큰 발급 (앱용) ==========

@app.route('/api/token', methods=['POST'])
@login_required
def api_token():
    """앱에서 사용할 JWT 토큰 발급"""
    user_id = session['user_id']
    token = issue_jwt(user_id)
    return jsonify({'token': token, 'expires_in_days': JWT_EXPIRE_DAYS})


# ========== 대시보드 ==========

@app.route('/')
@login_required
def index():
    user_id = session['user_id']
    if db is None:
        return render_template('index.html',
                               stats={'total_processed': 0, 'active_channels': 0, 'today_processed': 0},
                               recent_videos=[],
                               channels=[],
                               error="DB 초기화 실패",
                               current_user=get_current_user())

    stats = db.get_stats(user_id=user_id)
    recent_videos = db.get_processed_videos(limit=5, user_id=user_id)
    channels = db.get_channels(active_only=True, user_id=user_id)

    return render_template('index.html',
                           stats=stats,
                           recent_videos=recent_videos,
                           channels=channels,
                           current_user=get_current_user())


@app.route('/channels')
@login_required
def channels():
    user_id = session['user_id']
    if db is None:
        return render_template('channels.html', channels=[], current_user=get_current_user())
    all_channels = db.get_channels(user_id=user_id)
    return render_template('channels.html', channels=all_channels, current_user=get_current_user())


@app.route('/channels/add', methods=['POST'])
@login_required
def add_channel():
    user_id = session['user_id']
    if db is None:
        flash('DB 연결 실패', 'error')
        return redirect(url_for('channels'))

    channel_url = request.form.get('channel_url', '').strip()

    if not channel_url:
        flash('채널 URL을 입력해주세요.', 'error')
        return redirect(url_for('channels'))

    if 'youtube.com' not in channel_url and 'youtu.be' not in channel_url:
        flash('올바른 YouTube 채널 URL이 아닙니다.', 'error')
        return redirect(url_for('channels'))

    channel_name = extract_channel_name(channel_url) or request.form.get('channel_name')
    channel = db.add_channel(channel_url, channel_name, user_id=user_id)

    if channel:
        flash(f'채널 "{channel_name or channel_url}"이 추가되었습니다.', 'success')
        db.add_log('INFO', f'채널 추가: {channel_url}', 'web')
    else:
        flash('이미 등록된 채널입니다.', 'warning')

    return redirect(url_for('channels'))


@app.route('/channels/import-subscriptions', methods=['POST'])
@login_required
def import_subscriptions():
    """YouTube 구독 채널 자동 임포트"""
    user_id = session['user_id']
    user = db.get_user(user_id)

    if not user or not user.oauth_token:
        flash('YouTube 접근 권한이 없습니다. 다시 로그인해주세요.', 'error')
        return redirect(url_for('channels'))

    try:
        creds = Credentials.from_authorized_user_info(
            json.loads(user.oauth_token),
            scopes=LOGIN_SCOPES
        )
        youtube = build('youtube', 'v3', credentials=creds)

        imported = 0
        skipped = 0
        next_page_token = None

        while True:
            response = youtube.subscriptions().list(
                part='snippet',
                mine=True,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            for item in response.get('items', []):
                snippet = item['snippet']
                channel_id = snippet['resourceId']['channelId']
                channel_name = snippet['title']
                channel_url = f"https://www.youtube.com/channel/{channel_id}"

                result = db.add_channel(channel_url, channel_name, user_id=user_id)
                if result:
                    imported += 1
                else:
                    skipped += 1

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

        db.add_log('INFO', f'구독 채널 임포트: {imported}개 추가, {skipped}개 중복', 'web')
        flash(f'구독 채널 임포트 완료: {imported}개 추가, {skipped}개 이미 등록됨', 'success')

    except Exception as e:
        logger.error(f"구독 채널 임포트 실패: {e}")
        flash(f'구독 채널 임포트 실패: {e}', 'error')

    return redirect(url_for('channels'))


@app.route('/channels/<int:channel_id>/toggle', methods=['POST'])
@login_required
def toggle_channel(channel_id):
    channel = db.toggle_channel(channel_id)
    if channel:
        status = '활성화' if channel.is_active else '비활성화'
        flash(f'채널이 {status}되었습니다.', 'success')
    else:
        flash('채널을 찾을 수 없습니다.', 'error')
    return redirect(url_for('channels'))


@app.route('/channels/<int:channel_id>/delete', methods=['POST'])
@login_required
def delete_channel(channel_id):
    if db.delete_channel(channel_id):
        flash('채널이 삭제되었습니다.', 'success')
    else:
        flash('채널을 찾을 수 없습니다.', 'error')
    return redirect(url_for('channels'))


@app.route('/history')
@login_required
def history():
    user_id = session['user_id']
    if db is None:
        return render_template('history.html', videos=[], page=1, total_pages=1, total=0,
                               current_user=get_current_user())

    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    videos = db.get_processed_videos(limit=per_page, offset=offset, user_id=user_id)
    stats = db.get_stats(user_id=user_id)

    total = stats['total_processed']
    total_pages = (total + per_page - 1) // per_page

    return render_template('history.html',
                           videos=videos,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           get_failure_reason_display=get_failure_reason_display,
                           current_user=get_current_user())


@app.route('/logs')
@login_required
def logs():
    level = request.args.get('level')
    log_entries = db.get_logs(limit=200, level=level) if db else []

    file_logs = []
    log_file = os.path.join('data', 'app.log')
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-100:]
                file_logs = [line.strip() for line in lines if line.strip()]
        except Exception as e:
            logger.error(f"로그 파일 읽기 실패: {e}")

    return render_template('logs.html',
                           db_logs=log_entries,
                           file_logs=file_logs,
                           current_level=level,
                           current_user=get_current_user())


@app.route('/logs/clear', methods=['POST'])
@login_required
def clear_logs():
    try:
        log_file = os.path.join('data', 'app.log')
        if os.path.exists(log_file):
            open(log_file, 'w').close()
        flash('로그가 초기화되었습니다.', 'success')
    except Exception as e:
        flash(f'로그 초기화 실패: {e}', 'error')
    return redirect(url_for('logs'))


# ========== 설정 페이지 ==========

@app.route('/settings')
@login_required
def settings():
    google_connected = os.path.exists(TOKEN_PATH)
    google_email = None

    if google_connected:
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, DRIVE_SCOPES)
            if creds and creds.valid:
                service = build('oauth2', 'v2', credentials=creds)
                user_info = service.userinfo().get().execute()
                google_email = user_info.get('email')
        except Exception as e:
            logger.error(f"Google 사용자 정보 조회 실패: {e}")
            google_connected = False

    has_credentials_file = os.path.exists(CREDENTIALS_PATH)

    return render_template('settings.html',
                           google_connected=google_connected,
                           google_email=google_email,
                           has_credentials_file=has_credentials_file,
                           drive_folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_ID', ''),
                           check_interval=os.getenv('CHECK_INTERVAL_HOURS', '1'),
                           tts_method=os.getenv('TTS_METHOD', 'gtts'),
                           current_user=get_current_user())


# ========== Google Drive OAuth (기존 유지) ==========

@app.route('/oauth/google')
@login_required
def oauth_google():
    if not os.path.exists(CREDENTIALS_PATH):
        flash('google_credentials.json 파일이 없습니다.', 'error')
        return redirect(url_for('settings'))

    try:
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_PATH,
            scopes=DRIVE_SCOPES + ['https://www.googleapis.com/auth/userinfo.email'],
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
        logger.error(f"Drive OAuth 시작 실패: {e}")
        flash(f'Drive 연동 시작 실패: {e}', 'error')
        return redirect(url_for('settings'))


@app.route('/oauth/callback')
def oauth_callback():
    try:
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_PATH,
            scopes=DRIVE_SCOPES + ['https://www.googleapis.com/auth/userinfo.email'],
            redirect_uri=url_for('oauth_callback', _external=True)
        )
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials

        with open(TOKEN_PATH, 'w') as token_file:
            token_file.write(credentials.to_json())

        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        email = user_info.get('email', 'Unknown')

        if db:
            db.add_log('INFO', f'Google Drive 연동 완료: {email}', 'oauth')

        flash(f'Google Drive 연동 성공! ({email})', 'success')
        return redirect(url_for('settings'))

    except Exception as e:
        logger.error(f"Drive OAuth 콜백 실패: {e}")
        flash(f'Google Drive 연동 실패: {e}', 'error')
        return redirect(url_for('settings'))


@app.route('/oauth/disconnect', methods=['POST'])
@login_required
def oauth_disconnect():
    try:
        if os.path.exists(TOKEN_PATH):
            os.remove(TOKEN_PATH)
        if db:
            db.add_log('INFO', 'Google Drive 연동 해제', 'oauth')
        flash('Google Drive 연동이 해제되었습니다.', 'success')
    except Exception as e:
        flash(f'연동 해제 실패: {e}', 'error')
    return redirect(url_for('settings'))


# ========== 실패 영상 ==========

@app.route('/failed')
@login_required
def failed_videos():
    user_id = session['user_id']
    if db is None:
        return render_template('failed.html', videos=[], retryable_count=0, non_retryable_count=0,
                               current_user=get_current_user())

    all_failed = db.get_failed_videos(include_non_retryable=True)
    retryable = [v for v in all_failed if v.is_retryable and v.retry_count < 3]
    non_retryable = [v for v in all_failed if not v.is_retryable or v.retry_count >= 3]

    return render_template('failed.html',
                           videos=all_failed,
                           retryable_count=len(retryable),
                           non_retryable_count=len(non_retryable),
                           get_failure_reason_display=get_failure_reason_display,
                           current_user=get_current_user())


# ========== API 엔드포인트 ==========

@app.route('/api/stats')
@api_login_required
def api_stats():
    user_id = session.get('user_id')
    return jsonify(db.get_stats(user_id=user_id))


@app.route('/api/channels')
@api_login_required
def api_channels():
    user_id = session.get('user_id')
    channels = db.get_channels(user_id=user_id)
    return jsonify([c.to_dict() for c in channels])


@app.route('/api/videos')
@api_login_required
def api_videos():
    user_id = session.get('user_id')
    limit = request.args.get('limit', 50, type=int)
    videos = db.get_processed_videos(limit=limit, user_id=user_id)
    return jsonify([v.to_dict() for v in videos])


@app.route('/api/process', methods=['POST'])
@api_login_required
def api_process_video():
    video_url = request.json.get('video_url')
    if not video_url:
        return jsonify({'error': 'video_url required'}), 400

    db.add_log('INFO', f'수동 처리 요청: {video_url}', 'api')

    try:
        import yt_dlp
        from processor import SimpleProcessor

        ydl_opts = {'quiet': True, 'extract_flat': False}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            video_id = info['id']
            title = info.get('title', 'Unknown')
            channel = info.get('uploader', 'Unknown')

        if db.is_video_processed(video_id):
            return jsonify({'error': '이미 처리된 영상입니다', 'video_id': video_id}), 409

        video = {'id': video_id, 'title': title, 'url': video_url, 'channel': channel}
        config = Config()
        processor = SimpleProcessor(config)
        success = processor.process_video(video)

        if success:
            db.add_log('INFO', f'수동 처리 완료: {title}', 'api')
            return jsonify({'status': 'completed', 'video_id': video_id, 'title': title})
        else:
            failed_video = db.session.query(ProcessedVideo).filter_by(video_id=video_id).first()
            error_msg = failed_video.error_message if failed_video else '처리 실패'
            failure_reason = failed_video.failure_reason if failed_video else None
            return jsonify({
                'status': 'failed',
                'video_id': video_id,
                'title': title,
                'error': error_msg,
                'failure_reason': failure_reason,
                'failure_reason_display': get_failure_reason_display(failure_reason) if failure_reason else None
            }), 500

    except Exception as e:
        error_msg = str(e)
        logger.error(f"수동 처리 에러: {error_msg}")
        db.add_log('ERROR', f'수동 처리 실패: {error_msg}', 'api')
        return jsonify({'error': error_msg}), 500


@app.route('/api/failed')
@api_login_required
def api_failed_videos():
    include_all = request.args.get('include_all', 'false').lower() == 'true'
    videos = db.get_failed_videos(include_non_retryable=include_all)
    result = []
    for v in videos:
        video_dict = v.to_dict()
        video_dict['failure_reason_display'] = get_failure_reason_display(v.failure_reason)
        video_dict['is_permanent_failure'] = is_permanent_failure(v.failure_reason) if v.failure_reason else False
        result.append(video_dict)
    return jsonify(result)


@app.route('/api/retry/<video_id>', methods=['POST'])
@api_login_required
def api_retry_video(video_id):
    try:
        from processor import SimpleProcessor
        config = Config()
        processor = SimpleProcessor(config)
        result = processor.retry_failed_video(video_id)
        if db:
            db.add_log(
                'INFO' if result['success'] else 'WARNING',
                f"재시도 {'성공' if result['success'] else '실패'}: {video_id} - {result['message']}",
                'api'
            )
        return jsonify(result)
    except Exception as e:
        logger.error(f"재시도 API 에러: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/retry-all', methods=['POST'])
@api_login_required
def api_retry_all():
    try:
        from processor import SimpleProcessor
        config = Config()
        processor = SimpleProcessor(config)
        result = processor.retry_all_failed()
        if db:
            db.add_log('INFO',
                f"전체 재시도 완료: 성공 {result['success']}, 실패 {result['failed']}, 스킵 {result['skipped']}",
                'api')
        return jsonify(result)
    except Exception as e:
        logger.error(f"전체 재시도 API 에러: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/delete-failed/<video_id>', methods=['DELETE'])
@app.route('/api/videos/<video_id>', methods=['DELETE'])
@api_login_required
def api_delete_video(video_id):
    try:
        success = db.delete_video_record(video_id)
        if success:
            db.add_log('INFO', f'영상 기록 삭제: {video_id}', 'api')
            return jsonify({'success': True, 'message': '기록이 삭제되었습니다.'})
        else:
            return jsonify({'success': False, 'message': '영상을 찾을 수 없습니다.'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ========== 템플릿 필터 ==========

@app.template_filter('timeago')
def timeago_filter(dt):
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
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_server(debug=True)
