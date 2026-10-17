FROM python:3.12-slim
ARG INSTALL_ML=false
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.12.13
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN if [ "$INSTALL_ML" = "true" ]; then uv sync --frozen --no-dev --extra ml; else uv sync --frozen --no-dev; fi
RUN useradd --create-home --uid 10001 appuser
USER appuser
ENV PATH="/opt/venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/api/health', timeout=2)"
CMD ["sh", "-c", "exec python -m uvicorn hackathon_backend.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers"]
