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
# Render injects PORT (default 10000); PORT=8000 keeps Compose/Caddy unchanged.
# FORWARDED_ALLOW_IPS="*" is safe only because the container is reachable solely
# through the host's TLS proxy (Render edge or Caddy).
ENV PORT=8000 FORWARDED_ALLOW_IPS="*"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=2)"
CMD ["sh", "-c", "export APP_DOMAIN=\"${APP_DOMAIN:-${RENDER_EXTERNAL_HOSTNAME:-}}\"; exec python -m uvicorn hackathon_backend.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers"]
