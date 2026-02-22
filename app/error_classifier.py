"""
YouTube 다운로드 에러 분류기
- 멤버십 컨텐츠, Rate Limit, 네트워크 오류 등 구분
- 재시도 가능 여부 판단
"""
import re
import logging

logger = logging.getLogger(__name__)

# 에러 유형 상수
ERROR_MEMBERSHIP = 'membership'      # 멤버십 전용 컨텐츠 (재시도 불가)
ERROR_PRIVATE = 'private'            # 비공개 영상 (재시도 불가)
ERROR_AGE_RESTRICTED = 'age_restricted'  # 연령 제한 (인증 필요)
ERROR_RATE_LIMIT = 'rate_limit'      # Rate limit (재시도 가능)
ERROR_NETWORK = 'network'            # 네트워크 오류 (재시도 가능)
ERROR_AUTH = 'auth'                  # 인증 오류 (설정 확인 필요)
ERROR_NOT_FOUND = 'not_found'        # 영상 없음 (재시도 불가)
ERROR_UNAVAILABLE = 'unavailable'    # 지역/국가 제한 등 (재시도 불가)
ERROR_UNKNOWN = 'unknown'            # 알 수 없는 오류 (재시도 가능)

# 멤버십 관련 에러 패턴
MEMBERSHIP_PATTERNS = [
    r'members[\s-]*only',
    r'available.*members',
    r'Join this channel',
    r'join.*to get access',
    r'membership.*required',
    r'멤버십.*전용',
    r'멤버.*전용',
    r'유료.*회원',
    r'구독자.*전용',
    r'This video is available to this channel',  # 멤버십 문구 변형
]

# 비공개 영상 패턴
PRIVATE_PATTERNS = [
    r'Private video',
    r'This video is private',
    r'비공개.*동영상',
    r'비공개.*영상',
]

# 연령 제한 패턴
AGE_RESTRICTED_PATTERNS = [
    r'age[\s-]*restrict',
    r'Sign in to confirm your age',
    r'연령.*제한',
    r'성인.*인증',
]

# Rate limit 패턴
RATE_LIMIT_PATTERNS = [
    r'rate[\s-]*limit',
    r'too many requests',
    r'HTTP Error 429',
    r'429.*Resource exhausted',
    r'Resource exhausted',
    r'quota exceeded',
    r'Please try again later',
]

# 네트워크 오류 패턴
NETWORK_PATTERNS = [
    r'Connection refused',
    r'Connection reset',
    r'timed?\s*out',
    r'Network is unreachable',
    r'Unable to download',
    r'urlopen error',
    r'socket error',
    r'ConnectionError',
    r'ReadTimeout',
    r'ConnectTimeout',
]

# 인증 오류 패턴
AUTH_PATTERNS = [
    r'Sign in',
    r'login required',
    r'로그인.*필요',
    r'authentication',
    r'Unauthorized',
    r'HTTP Error 401',
    r'HTTP Error 403',
]

# 영상 없음 패턴
NOT_FOUND_PATTERNS = [
    r'Video unavailable',
    r'This video has been removed',
    r'This video is no longer available',
    r'deleted video',
    r'HTTP Error 404',
    r'영상.*삭제',
    r'존재하지.*않',
]

# 지역/국가 제한 패턴
UNAVAILABLE_PATTERNS = [
    r'not available in your country',
    r'blocked.*country',
    r'geo[\s-]*restrict',
    r'지역.*제한',
    r'국가.*제한',
    r'The uploader has not made this video available',
]


def classify_error(error_message: str) -> tuple:
    """
    에러 메시지를 분석하여 에러 유형과 재시도 가능 여부 반환

    Returns:
        tuple: (failure_reason, is_retryable, description)
    """
    if not error_message:
        return ERROR_UNKNOWN, True, "에러 메시지 없음"

    error_str = str(error_message).lower()
    error_original = str(error_message)

    # 패턴 매칭 순서대로 검사 (우선순위 중요)

    # 1. 멤버십 컨텐츠 (재시도 불가)
    for pattern in MEMBERSHIP_PATTERNS:
        if re.search(pattern, error_original, re.IGNORECASE):
            return ERROR_MEMBERSHIP, False, "멤버십 전용 컨텐츠"

    # 2. 비공개 영상 (재시도 불가)
    for pattern in PRIVATE_PATTERNS:
        if re.search(pattern, error_original, re.IGNORECASE):
            return ERROR_PRIVATE, False, "비공개 영상"

    # 3. 영상 없음 (재시도 불가)
    for pattern in NOT_FOUND_PATTERNS:
        if re.search(pattern, error_original, re.IGNORECASE):
            return ERROR_NOT_FOUND, False, "영상이 삭제되었거나 존재하지 않음"

    # 4. 지역/국가 제한 (재시도 불가)
    for pattern in UNAVAILABLE_PATTERNS:
        if re.search(pattern, error_original, re.IGNORECASE):
            return ERROR_UNAVAILABLE, False, "지역 제한 또는 비공개 설정"

    # 5. 연령 제한 (인증 필요, 조건부 재시도)
    for pattern in AGE_RESTRICTED_PATTERNS:
        if re.search(pattern, error_original, re.IGNORECASE):
            return ERROR_AGE_RESTRICTED, True, "연령 제한 - 인증 필요"

    # 6. Rate Limit (재시도 가능)
    for pattern in RATE_LIMIT_PATTERNS:
        if re.search(pattern, error_original, re.IGNORECASE):
            return ERROR_RATE_LIMIT, True, "Rate limit - 잠시 후 재시도"

    # 7. 인증 오류 (조건부 재시도)
    for pattern in AUTH_PATTERNS:
        if re.search(pattern, error_original, re.IGNORECASE):
            return ERROR_AUTH, True, "인증 오류 - 쿠키/토큰 확인 필요"

    # 8. 네트워크 오류 (재시도 가능)
    for pattern in NETWORK_PATTERNS:
        if re.search(pattern, error_original, re.IGNORECASE):
            return ERROR_NETWORK, True, "네트워크 오류 - 재시도 가능"

    # 9. 알 수 없는 오류 (기본적으로 재시도 가능)
    return ERROR_UNKNOWN, True, "알 수 없는 오류"


def get_failure_reason_display(failure_reason: str) -> str:
    """에러 유형에 대한 한글 설명 반환"""
    display_map = {
        ERROR_MEMBERSHIP: "🔒 멤버십 전용",
        ERROR_PRIVATE: "🔒 비공개 영상",
        ERROR_AGE_RESTRICTED: "🔞 연령 제한",
        ERROR_RATE_LIMIT: "⏱️ 요청 제한",
        ERROR_NETWORK: "🌐 네트워크 오류",
        ERROR_AUTH: "🔑 인증 필요",
        ERROR_NOT_FOUND: "❌ 영상 없음",
        ERROR_UNAVAILABLE: "🚫 이용 불가",
        ERROR_UNKNOWN: "❓ 알 수 없음",
    }
    return display_map.get(failure_reason, "❓ 알 수 없음")


def is_permanent_failure(failure_reason: str) -> bool:
    """영구 실패인지 확인 (재시도해도 안 되는 경우)"""
    permanent_failures = {
        ERROR_MEMBERSHIP,
        ERROR_PRIVATE,
        ERROR_NOT_FOUND,
        ERROR_UNAVAILABLE,
    }
    return failure_reason in permanent_failures
