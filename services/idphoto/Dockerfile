# ============================================================
# HivisionIDPhotos sandbox shell — deliberately EMPTY.
#
# This image installs ONLY the apt-level system libraries that
# opencv / onnxruntime need. No Python packages, no application code.
# You install those BY HAND inside the running container, so the
# install is yours to understand rather than a black box.
#
# Base: CUDA 12.6 + cuDNN 9 runtime on Ubuntu 22.04 (-> python 3.10,
# which satisfies HivisionIDPhotos' numpy<=1.26.4 constraint).
#
# Broke your install? Throw the container away; this shell is unchanged:
#   docker compose rm -sf idphoto
#   docker compose --profile idphoto up -d idphoto
# Source code, model weights and the pip cache live on host bind
# mounts, so none of them are lost.
# ============================================================
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_CACHE_DIR=/root/.cache/pip

# libgl1 / libglib2.0-0 / libsm6 / libxext6 / libxrender1:
#   `import cv2` dies without these ("libGL.so.1: cannot open shared
#   object file"). Pre-installed because that error is obscure and has
#   nothing to do with HivisionIDPhotos itself.
# git / curl / vim / less: so the container is actually workable by hand.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip \
        git curl vim less ca-certificates \
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# 0-entrypoint.sh starts the WebUI if the pip deps are installed, and idles
# with instructions if they are not. It lives on the bind mount at
# /opt/idphoto (see docker-compose.yml), so editing it on the host takes
# effect on the next container start with no rebuild.
ENTRYPOINT ["/opt/idphoto/0-entrypoint.sh"]
