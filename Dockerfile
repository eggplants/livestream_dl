FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

COPY --from=denoland/deno:bin-2.5.6 /deno /usr/local/bin/deno
COPY --from=linuxserver/ffmpeg:8.0.1 /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=linuxserver/ffmpeg:8.0.1 /usr/local/bin/ffprobe /usr/local/bin/ffprobe

RUN chmod +x /usr/local/bin/deno /usr/local/bin/ffmpeg /usr/local/bin/ffprobe

RUN apt-get update && \
    apt-get install -y --no-install-recommends patch && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY . /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
RUN uv sync --locked --no-dev

RUN patch -u -d .venv/lib/*/site-packages/yt_dlp/extractor/youtube/ < yt-dlp.patch

ENV PATH="/app/.venv/bin:$PATH"
CMD ["uv", "run", "ls-dlp"]
