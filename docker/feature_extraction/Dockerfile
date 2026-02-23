# =============================================================================
# Feature Extraction Lambda - Docker Image
# Includes librosa, scipy, numpy for audio feature extraction
# =============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Configure numba for Lambda environment
ENV NUMBA_DISABLE_JIT=1
ENV NUMBA_CACHE_DIR=/tmp/numba_cache
RUN mkdir -p /tmp/numba_cache

# Install imageio-ffmpeg which bundles a compatible ffmpeg binary
# This is the most reliable way to get ffmpeg in Lambda
RUN pip install --no-cache-dir imageio-ffmpeg && \
    python3 -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" && \
    ln -s $(python3 -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())") /usr/local/bin/ffmpeg && \
    ffmpeg -version

# Install Python dependencies for audio processing
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

# Install librosa 0.9.2
RUN pip install --no-cache-dir 'librosa==0.9.2'

# Pre-compile numba functions
RUN python3 -c "import librosa; print('librosa pre-compiled successfully')"

# Copy shared utilities
COPY shared/ /var/task/shared/

# Copy Lambda handler
COPY lambdas/feature_extraction/handler.py /var/task/handler.py

# Set the handler
CMD ["handler.lambda_handler"]