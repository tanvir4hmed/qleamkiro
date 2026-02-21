# =============================================================================
# Feature Extraction Lambda - Docker Image
# Includes librosa, scipy, numpy for audio feature extraction
# =============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Download and extract ffmpeg using Python (no package manager needed)
# Using johnvansickle static builds - reliable and self-contained
RUN python3 -c "import urllib.request, tarfile, os, shutil; urllib.request.urlretrieve('https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz', '/tmp/ffmpeg.tar.xz'); tarfile.open('/tmp/ffmpeg.tar.xz', 'r:xz').extractall('/tmp'); [shutil.copy(f'/tmp/{n}/ffmpeg', '/usr/local/bin/ffmpeg') or shutil.copy(f'/tmp/{n}/ffprobe', '/usr/local/bin/ffprobe') for n in os.listdir('/tmp') if n.startswith('ffmpeg-') and os.path.isdir(f'/tmp/{n}')]; os.chmod('/usr/local/bin/ffmpeg', 0o755); os.chmod('/usr/local/bin/ffprobe', 0o755)" && rm -rf /tmp/ffmpeg* && /usr/local/bin/ffmpeg -version

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