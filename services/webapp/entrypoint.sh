#!/usr/bin/env bash
set -e

# Upgrade yt-dlp to latest on every container start
echo "[entrypoint] Upgrading yt-dlp to latest version..."
if pip install --no-cache-dir --upgrade yt-dlp 2>&1 | tail -3; then
    echo "[entrypoint] yt-dlp version: $(yt-dlp --version)"
else
    echo "[entrypoint] WARNING: yt-dlp upgrade failed, continuing with existing version"
fi

exec uvicorn main:app --host 0.0.0.0 --port 8080
