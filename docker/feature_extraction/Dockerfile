# =============================================================================
# Feature Extraction Lambda - Docker Image
# Includes librosa, scipy, numpy for audio feature extraction
# =============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Disable numba JIT caching (Lambda has read-only filesystem for packages)
ENV NUMBA_DISABLE_JIT=1

# Install requests for ffmpeg download script
RUN pip install requests

# Copy and run ffmpeg installation script
COPY docker/feature_extraction/install_ffmpeg.py /tmp/install_ffmpeg.py
RUN python3 /tmp/install_ffmpeg.py && \
    rm -rf /tmp/ffmpeg* /tmp/install_ffmpeg.py && \
    /usr/local/bin/ffmpeg -version

# Install Python dependencies for audio processing
# Using ffmpeg for audio loading (handles all formats), soundfile for reading ffmpeg output
# soxr for high-quality resampling, audioread required by librosa at import time
# scikit-learn required by librosa.effects.trim
# numba required by librosa.filters
RUN pip install --no-cache-dir --only-binary=:all: \
    'numpy==1.26.4' \
    'scipy==1.11.4' \
    'soundfile==0.12.1' \
    'soxr==0.3.7' \
    'audioread>=3.0.0' \
    'scikit-learn==1.3.2' \
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

# Install librosa
RUN pip install --no-cache-dir \
    'librosa==0.10.2.post1'

# Copy shared utilities
COPY shared/ /var/task/shared/

# Copy Lambda handler
COPY lambdas/feature_extraction/handler.py /var/task/handler.py

# Set the handler
CMD ["handler.lambda_handler"]