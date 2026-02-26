# =============================================================================
# Developmental Tracker Lambda - Docker Image
# Tracks CBR trend, VTL growth, milestone logging, and φ order parameter
# =============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Install Python dependencies (pre-built wheels only)
RUN pip install --no-cache-dir --only-binary=:all: \
    'boto3==1.34.0'

# Copy shared utilities
COPY shared/ /var/task/shared/

# Copy Lambda handler
COPY lambdas/developmental_tracker/handler.py /var/task/handler.py

# Set the handler
CMD ["handler.lambda_handler"]
