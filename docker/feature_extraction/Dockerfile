# =============================================================================
# Feature Extraction Lambda - Docker Image
# Includes librosa, scipy, numpy for audio feature extraction
# =============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Install system dependencies for audio processing
RUN yum install -y -q libsndfile && \
    yum clean all

# Install Python dependencies for audio processing
# Using specific versions to ensure compatibility
RUN pip install --no-cache-dir \
    'numpy>=1.24.0,<2' \
    'scipy>=1.11.0' \
    'librosa>=0.10.0' \
    'soundfile>=0.12.1' \
    'boto3>=1.28.0'

# Copy shared utilities
COPY shared/ /var/task/shared/

# Copy Lambda handler
COPY lambdas/feature_extraction/handler.py /var/task/handler.py

# Set the handler
CMD ["handler.lambda_handler"]