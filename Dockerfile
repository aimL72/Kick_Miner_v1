FROM python:3.12-slim

LABEL org.opencontainers.image.title="Kick Channel Points Miner" \
      org.opencontainers.image.description="A pure Kick channel-points farming bot"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl_cffi ships a manylinux wheel with libcurl-impersonate bundled,
# so no compiler / -dev packages are needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/logs /app/data

EXPOSE 5000
CMD ["python", "main.py"]
