FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

# Install system dependencies: noVNC, websockify, supervisor, yt-dlp (for validation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    novnc \
    websockify \
    supervisor \
    xvfb \
    x11vnc \
    fluxbox \
    dbus-x11 \
    x11-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Force-remove system-managed typing_extensions (no RECORD file) before pip install
RUN rm -rf /usr/lib/python3/dist-packages/typing_extensions* \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir yt-dlp \
    && playwright install chromium --with-deps

# Create stable symlink for Chromium binary (avoids hardcoding Playwright version)
RUN ln -sf "$(find /ms-playwright -path '*/chrome-linux/chrome' | head -1)" /usr/local/bin/chromium

# Supervisor config to run all processes
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

COPY . .

# noVNC on 6901, health API on 6902
EXPOSE 6901 6902

# Entrypoint upgrades yt-dlp on every start, then launches supervisor
ENTRYPOINT ["/app/entrypoint.sh"]
