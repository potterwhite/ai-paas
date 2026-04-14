#!/usr/bin/env bash
# Wait for Xvfb to be ready, then launch Chromium for noVNC manual login.
for _ in {1..30}; do
    if xdpyinfo -display :99 >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Remove stale lock files left by unclean container shutdowns
rm -f /data/chrome-profile/SingletonLock \
      /data/chrome-profile/SingletonSocket \
      /data/chrome-profile/SingletonCookie

exec /usr/local/bin/chromium \
    --display=:99 \
    --no-sandbox \
    --disable-gpu \
    --disable-software-rasterizer \
    --disable-dev-shm-usage \
    --user-data-dir=/data/chrome-profile \
    --start-maximized \
    https://www.youtube.com
