FROM python:3.14-slim
WORKDIR /app
RUN sed -i "s|http://deb.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g; s|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g" /etc/apt/sources.list.d/debian.sources
RUN apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN pip install --no-cache-dir --index-url https://mirrors.aliyun.com/pypi/simple uv==0.12.13
RUN UV_HTTP_TIMEOUT=120 uv sync --locked --no-dev --no-editable
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY alembic.ini ./
COPY migrations ./migrations
RUN useradd --create-home app
USER app
EXPOSE 8000
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
