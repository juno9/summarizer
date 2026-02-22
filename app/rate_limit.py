"""
Rate Limit 최적화 설정
"""
import logging
import time
import random

logger = logging.getLogger(__name__)

class RateLimitManager:
    """YouTube Rate Limit 관리자"""
    
    def __init__(self):
        self.last_request_time = {}
        self.min_interval = 2  # 최소 요청 간격 (초)
        self.max_retries = 3
        self.base_delay = 5  # 기본 지연 시간 (초)
    
    def wait_before_request(self, endpoint="default"):
        """요청 전 대기"""
        now = time.time()
        
        if endpoint in self.last_request_time:
            elapsed = now - self.last_request_time[endpoint]
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed + random.uniform(0.5, 2.0)
                logger.info(f"Rate limit 방지: {wait_time:.1f}초 대기...")
                time.sleep(wait_time)
        
        self.last_request_time[endpoint] = time.time()
    
    def handle_rate_limit(self, attempt):
        """Rate limit 발생 시 처리"""
        if attempt >= self.max_retries:
            return False
        
        # 지수 백오프
        delay = self.base_delay * (2 ** attempt) + random.uniform(1, 5)
        logger.warning(f"Rate limit 발생! {delay:.1f}초 대기 (시도 {attempt + 1}/{self.max_retries})")
        time.sleep(delay)
        
        return True
    
    def get_random_delay(self, min_delay=1, max_delay=3):
        """랜덤 지연 시간 생성"""
        return random.uniform(min_delay, max_delay)

# 전역 Rate Limit 관리자
rate_manager = RateLimitManager()