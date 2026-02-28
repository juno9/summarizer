"""
GPU 가속 Whisper 프로세서
- Windows/Linux NVIDIA GPU → faster-whisper (CUDA) + BatchedInferencePipeline
- macOS Apple Silicon → mlx-whisper (Metal)
- 그 외 → faster-whisper (CPU fallback)
"""
import os
import sys
import platform
import logging

logger = logging.getLogger(__name__)

# 싱글톤 모델
_whisper_model = None
_batched_pipeline = None
_model_backend = None  # 'cuda', 'mlx', 'cpu'


def _is_apple_silicon():
    """Apple Silicon 여부 확인"""
    return platform.system() == 'Darwin' and platform.machine() == 'arm64'


def _get_mlx_model(model_size):
    """Apple Silicon용 mlx-whisper 모델"""
    try:
        import mlx_whisper
        logger.info(f"mlx-whisper 모델 로딩: {model_size}")
        return mlx_whisper
    except ImportError:
        logger.warning("mlx-whisper 설치 안됨. 설치: pip install mlx-whisper")
        return None


def _get_faster_whisper_model(model_size):
    """NVIDIA GPU 또는 CPU용 faster-whisper 모델 + BatchedInferencePipeline"""
    from faster_whisper import WhisperModel, BatchedInferencePipeline

    # CUDA 먼저 시도
    try:
        logger.info(f"faster-whisper GPU 모델 로딩: {model_size}")
        model = WhisperModel(
            model_size,
            device="cuda",
            compute_type="float16",
            device_index=0
        )
        batched = BatchedInferencePipeline(model=model)
        logger.info("faster-whisper GPU 모델 + BatchedInferencePipeline 로딩 완료")
        return model, batched, "cuda"
    except Exception as e:
        logger.warning(f"GPU 모델 로딩 실패: {e}")
        logger.info("faster-whisper CPU 모드로 fallback...")
        model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8"
        )
        batched = BatchedInferencePipeline(model=model)
        logger.info("faster-whisper CPU 모델 + BatchedInferencePipeline 로딩 완료")
        return model, batched, "cpu"


def get_optimized_whisper_model():
    """플랫폼에 맞는 최적화된 Whisper 모델 반환"""
    global _whisper_model, _batched_pipeline, _model_backend

    if _whisper_model is None:
        model_size = os.getenv('WHISPER_MODEL', 'large-v3-turbo')

        # Apple Silicon이면 mlx-whisper 시도
        if _is_apple_silicon():
            mlx = _get_mlx_model(model_size)
            if mlx:
                _whisper_model = mlx
                _model_backend = "mlx"
                logger.info("Apple Silicon - mlx-whisper 사용")
                return _whisper_model

            logger.info("mlx-whisper 실패, faster-whisper CPU로 fallback")

        # Windows/Linux 또는 mlx 실패시 faster-whisper
        _whisper_model, _batched_pipeline, _model_backend = _get_faster_whisper_model(model_size)

    return _whisper_model


def transcribe_with_gpu(audio_file, language='ko'):
    """플랫폼에 맞는 음성 인식 (BatchedInferencePipeline 사용)"""
    global _model_backend, _batched_pipeline

    model = get_optimized_whisper_model()
    model_size = os.getenv('WHISPER_MODEL', 'large-v3-turbo')

    logger.info(f"음성 인식 시작 ({_model_backend}): {audio_file}")

    try:
        if _model_backend == "mlx":
            # mlx-whisper 사용
            result = model.transcribe(
                audio_file,
                path_or_hf_repo=f"mlx-community/whisper-{model_size}-mlx",
                language=language
            )
            full_text = result.get("text", "")
        else:
            # faster-whisper BatchedInferencePipeline 사용 (최대 4배 빠름)
            segments, info = _batched_pipeline.transcribe(
                audio_file,
                language=language,
                batch_size=16,
                vad_filter=True,
            )
            full_text = ""
            for segment in segments:
                full_text += segment.text + " "

        logger.info(f"음성 인식 완료 ({_model_backend}): {len(full_text)}자")
        return full_text.strip()

    except Exception as e:
        logger.error(f"음성 인식 실패: {e}")
        # CUDA 실패 시 싱글톤 리셋 후 CPU로 재시도
        if _model_backend == "cuda":
            logger.info("CUDA 실패, CPU 모드로 싱글톤 리셋 후 재시도...")
            _whisper_model = None
            _batched_pipeline = None
            _model_backend = None
            try:
                from faster_whisper import WhisperModel, BatchedInferencePipeline
                cpu_model = WhisperModel(model_size, device="cpu", compute_type="int8")
                cpu_batched = BatchedInferencePipeline(model=cpu_model)
                _whisper_model = cpu_model
                _batched_pipeline = cpu_batched
                _model_backend = "cpu"
                logger.info("CPU 모드 전환 완료, 재시도...")
                segments, info = cpu_batched.transcribe(
                    audio_file,
                    language=language,
                    batch_size=8,
                    vad_filter=True,
                )
                full_text = ""
                for segment in segments:
                    full_text += segment.text + " "
                logger.info(f"CPU 음성 인식 완료: {len(full_text)}자")
                return full_text.strip()
            except Exception as cpu_e:
                logger.error(f"CPU 재시도 실패: {cpu_e}")
                raise cpu_e
        raise
