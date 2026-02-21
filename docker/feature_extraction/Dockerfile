# =============================================================================
# Feature Extraction Lambda - Docker Image
# Includes librosa, scipy, numpy for audio feature extraction
# =============================================================================
# Use :3.11; install step below supports both yum (AL2) and dnf (AL2023) so base updates don't break the build.
FROM public.ecr.aws/lambda/python:3.11

# FFmpeg: fixed BtbN release (no "latest" tag); must be declared before the RUN that uses them
ARG FFMPEG_TAG=autobuild-2026-02-21-13-00
ARG FFMPEG_ASSET=ffmpeg-n7.1.3-40-gcddd06f3b9-linux64-gpl-7.1.tar.xz

# Install system deps + FFmpeg in one RUN so curl is available when used (avoids exit 127).
# libsndfile for soundfile; curl + xz for FFmpeg. Support both yum (AL2) and dnf (AL2023).
RUN set -e; \
    if command -v dnf >/dev/null 2>&1; then \
      dnf install -y libsndfile curl xz && dnf clean all; \
    else \
      yum install -y libsndfile curl xz && yum clean all; \
    fi; \
    /usr/bin/curl -fsSL "https://github.com/BtbN/FFmpeg-Builds/releases/download/${FFMPEG_TAG}/${FFMPEG_ASSET}" -o /tmp/ffmpeg.tar.xz; \
    tar -xf /tmp/ffmpeg.tar.xz -C /tmp; \
    cp /tmp/ffmpeg-*/bin/ffmpeg /usr/local/bin/; \
    cp /tmp/ffmpeg-*/bin/ffprobe /usr/local/bin/; \
    chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe; \
    rm -rf /tmp/ffmpeg*; \
    /usr/local/bin/ffmpeg -version

# Install Python dependencies for audio processing
# Using ffmpeg for audio loading (handles all formats), soundfile for reading ffmpeg output
# soxr for high-quality resampling, audioread required by librosa at import time
RUN pip install --no-cache-dir --only-binary=:all: \
    'numpy==1.26.4' \
    'scipy==1.11.4' \
    'soundfile==0.12.1' \
    'soxr==0.3.7' \
    'audioread>=3.0.0' \
    'joblib>=1.2.0' \
    'decorator>=5.0.0' \
    'lazy_loader>=0.1' \
    'msgpack>=1.0.0' \
    'platformdirs>=2.5.0' \
    'pooch>=1.0.0' \
    'typer>=0.10.0' \
    'boto3==1.34.0'

# Install librosa without numba dependencies
RUN pip install --no-cache-dir \
    'librosa==0.10.2.post1' \
    --no-deps

# Copy shared utilities
COPY shared/ /var/task/shared/

# Copy Lambda handler
COPY lambdas/feature_extraction/handler.py /var/task/handler.py

# Set the handler
CMD ["handler.lambda_handler"]