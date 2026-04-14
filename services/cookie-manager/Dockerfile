FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

# Install system dependencies: noVNC, websockify, supervisor, yt-dlp (for validation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    novnc \
    websockify \
    supervisor \
    xvfb \
    x11vnc \
    fluxbox \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir yt-dlp \
    && playwright install chromium --with-deps

# Supervisor config to run all processes
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

COPY . .

# noVNC on 6901, health API on 6902
EXPOSE 6901 6902

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
