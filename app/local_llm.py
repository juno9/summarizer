"""
로컬 LLM 요약기 - Ollama + RTX 4060 Ti 최적화
"""
import requests
import logging
import json
from typing import Optional

logger = logging.getLogger(__name__)

class LocalLLMSummarizer:
    def __init__(self, model_name="llama3.2:3b"):
        self.base_url = "http://localhost:11434"
        self.model_name = model_name  # 3B 모델로 GP 메모리 효율적
        self.timeout = 180  # 3분으로 타임아웃 증가
        self.base_url = "http://localhost:11434"
        self.model_name = model_name  # 3B 모델로 8GB VRAM 최적화
        self.timeout = 120  # 2분 타임아웃
        
    def check_ollama_status(self) -> bool:
        """Ollama 서비스 상태 확인"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def ensure_model_downloaded(self) -> bool:
        """모델 다운로드 확인"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            models = response.json().get('models', [])
            
            model_exists = any(self.model_name in model['name'] for model in models)
            if not model_exists:
                logger.error(f"모델 {self.model_name}가 설치되지 않음")
                logger.info(f"실행 명령어: ollama pull {self.model_name}")
                return False
            
            return True
        except:
            return False
    
    def extract_transcript(self, text: str, max_chars: int = 50000) -> str:
        """로컬 LLM으로 텍스트 요약"""
        # 텍스트 길이 제한 (RTX 4060 Ti 최적화)
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
            logger.warning(f"텍스트 길이 제한: {max_chars}자로 축소")
        
        if not self.check_ollama_status():
            logger.error("Ollama 서비스를 찾을 수 없음")
            return self._fallback_summary(text)
        
        if not self.ensure_model_downloaded():
            return self._fallback_summary(text)
        
        # 한글 최적화 프롬프트 - 일관성 있는 상세 요약
        summary_prompt = f"""다음은 유튜브 영상의 한국어 내용입니다. 영상의 내용을 정확하고 구체적으로 분석하여 요약해주세요.

요약 지침:
1. 반드시 영상에 포함된 실제 내용만 사용하세요
2. 구체적인 사실, 데이터, 예시가 있다면 반드시 포함해주세요
3. 주제와 논점을 명확하게 구분해주세요
4. 결론은 영상의 핵심 메시지를 요약해야 합니다

원문 내용:
{text}

요약:"""

        try:
            logger.info("로컬 LLM 요약 시작...")
            
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,      # 더 유연한 응답
                        "top_p": 0.9,
                        "repeat_penalty": 1.05,   # 반복 방지
                        "num_predict": 1500,  # 응답 길이 제한
                        "num_ctx": 4096,      # 컨텍스트 길이 최적화
                        "num_gpu_layers": -1, # GPU 전체 활용
                        "use_mlock": True,     # RAM 고정 (성능 향상)
                        "mirostat": 0.8       # 균형화된 품질
                    }
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                summary = result.get('response', '').strip()
                logger.info(f"로컬 LLM 요약 완료: {len(summary)}자")
                return summary
            else:
                logger.error(f"LLM 응답 오류: {response.status_code}")
                return self._fallback_summary(text)
                
        except requests.exceptions.Timeout:
            logger.error("LLM 요청 타임아웃")
            return self._fallback_summary(text)
        except Exception as e:
            logger.error(f"로컬 LLM 요약 실패: {e}")
            return self._fallback_summary(text)
    
    def _fallback_summary(self, text: str) -> str:
        """간단한 fallback 요약"""
        # 첫 500자로 간단한 요약 생성
        preview = text[:500] + ("..." if len(text) > 500 else "")
        return f"요약 실패 - 원본 미리보기:\n{preview}"