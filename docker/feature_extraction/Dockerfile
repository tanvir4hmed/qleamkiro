# =============================================================================
# Feature Extraction Lambda - Docker Image
# Includes librosa, scipy, numpy for audio feature extraction
# =============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Disable numba JIT caching (Lambda has read-only filesystem for packages)
ENV NUMBA_DISABLE_JIT=1
ENV NUMBA_CACHE_DIR=/tmp/numba_cache

# Install system dependencies for audio processing
RUN yum install -y -q libsndfile && \
    yum clean all

# Install Python dependencies for audio processing
# Using specific versions with pre-built wheels (no compilation required)
# IMPORTANT: Only use versions that have manylinux wheels available
RUN pip install --no-cache-dir --only-binary=:all: \
    'numpy==1.26.4' \
    'scipy==1.11.4' \
    'librosa==0.10.1' \
    'soundfile==0.12.1' \
    'boto3==1.34.0' \
    'numba==0.58.1' \
    'llvmlite==0.41.1'

# Copy shared utilities
COPY shared/ /var/task/shared/

# Copy Lambda handler
COPY lambdas/feature_extraction/handler.py /var/task/handler.py

# Set the handler
CMD ["handler.lambda_handler"]