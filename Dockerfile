FROM python:3.10-slim

WORKDIR /app

# 시스템 패키지
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# deno 설치 (yt-dlp JavaScript 런타임)
RUN curl -fsSL https://deno.land/install.sh | sh
ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

# Python 패키지
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --upgrade yt-dlp && \
    pip install openai-whisper

# 앱 복사
COPY app/ /app/
COPY templates/ /app/templates/
COPY static/ /app/static/

# 디렉토리 생성
RUN mkdir -p /tmp/youtube_temp /app/data /app/credentials

# 포트 노출
EXPOSE 5000

CMD ["python", "main.py"]
