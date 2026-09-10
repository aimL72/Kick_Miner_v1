FROM python:3.12-slim

LABEL org.opencontainers.image.title="Kick Channel Points Miner" \
      org.opencontainers.image.description="A pure Kick channel-points farming bot" \
      org.opencontainers.image.source="https://github.com/aimL72/Kick_Miner_v1"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    KICK_MINER_DATA=/data

WORKDIR /app

# curl_cffi ships a manylinux wheel with libcurl-impersonate bundled - no
# compiler or -dev packages needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# config.json, logs/ and data/ all live under /data (one volume to mount)
RUN mkdir -p /data && rm -f /app/config.json
VOLUME /data

EXPOSE 5000
CMD ["python", "main.py"]
