FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    NEURODYNAMIC_STATE=/data/mcp NEURODYNAMIC_TOTAL_CAP_ATOMIC=0
WORKDIR /app
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml README.md LICENSE ./
COPY neurodynamic_mcp ./neurodynamic_mcp
RUN python -m pip install --no-cache-dir --no-deps . \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin mcp \
    && mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
ENTRYPOINT ["neurodynamic-mcp"]
