# =============================================================================
# Feature Extraction Lambda - Docker Image
# Includes librosa, scipy, numpy for audio feature extraction
# =============================================================================

# Stage 1: Download ffmpeg using a full image with curl
FROM alpine:3.19 AS ffmpeg-downloader

# Install curl for downloading
RUN apk add --no-cache curl xz

# Download ffmpeg static build with retry
RUN curl -L --retry 5 --retry-delay 3 --max-time 300 \
    -o /tmp/ffmpeg.tar.xz \
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz" && \
    cd /tmp && \
    tar -xf ffmpeg.tar.xz && \
    mv ffmpeg-master-latest-linux64-gpl/bin/ffmpeg /tmp/ffmpeg && \
    mv ffmpeg-master-latest-linux64-gpl/bin/ffprobe /tmp/ffprobe

# Stage 2: Main Lambda image
FROM public.ecr.aws/lambda/python:3.11

# Configure numba for Lambda environment
# - Disable JIT compilation (runs in pure Python mode, avoids caching issues)
# - Set cache directory to /tmp as fallback
ENV NUMBA_DISABLE_JIT=1
ENV NUMBA_CACHE_DIR=/tmp/numba_cache
RUN mkdir -p /tmp/numba_cache

# Copy ffmpeg from the downloader stage
COPY --from=ffmpeg-downloader /tmp/ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg-downloader /tmp/ffprobe /usr/local/bin/ffprobe
RUN chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe && \
    ffmpeg -version

# Install Python dependencies for audio processing
# Using ffmpeg for audio loading (handles all formats), soundfile for reading ffmpeg output
# soxr for high-quality resampling, audioread required by librosa at import time
# scikit-learn required by librosa.effects.trim
# numba required by librosa.filters
RUN pip install --no-cache-dir --only-binary=:all: \
    'numpy==1.24.4' \
    'scipy==1.10.1' \
    'soundfile==0.12.1' \
    'soxr==0.3.7' \
    'audioread>=3.0.0' \
    'scikit-learn==1.3.0' \
    'numba==0.58.1' \
    'llvmlite==0.41.1' \
    'joblib>=1.2.0' \
    'decorator>=5.0.0' \
    'lazy_loader>=0.1' \
    'msgpack>=1.0.0' \
    'platformdirs>=2.5.0' \
    'pooch>=1.0.0' \
    'typer>=0.10.0' \
    'boto3==1.34.0'

# Install librosa 0.9.2 (fewer numba dependencies, works better in Lambda)
RUN pip install --no-cache-dir \
    'librosa==0.9.2'

# Pre-compile numba functions by importing librosa during build
# This caches the JIT-compiled functions in the image
RUN python3 -c "import librosa; print('librosa pre-compiled successfully')"

# Copy shared utilities
COPY shared/ /var/task/shared/

# Copy Lambda handler
COPY lambdas/feature_extraction/handler.py /var/task/handler.py

# Set the handler
CMD ["handler.lambda_handler"]