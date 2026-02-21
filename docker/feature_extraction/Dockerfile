# =============================================================================
# Feature Extraction Lambda - Docker Image
# Includes librosa, scipy, numpy for audio feature extraction
# =============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Install system dependencies for audio processing
# libsndfile for soundfile library
# Download static ffmpeg binary (ffmpeg not available in Amazon Linux repos)
RUN yum install -y libsndfile curl xz && \
    curl -L https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz -o /tmp/ffmpeg.tar.xz && \
    tar -xf /tmp/ffmpeg.tar.xz -C /tmp && \
    cp /tmp/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg /usr/local/bin/ && \
    cp /tmp/ffmpeg-master-latest-linux64-gpl/bin/ffprobe /usr/local/bin/ && \
    chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe && \
    rm -rf /tmp/ffmpeg* && \
    yum clean all && \
    ffmpeg -version

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