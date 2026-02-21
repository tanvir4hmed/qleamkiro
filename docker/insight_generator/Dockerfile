# =============================================================================
# Insight Generator Lambda - Docker Image
# Includes boto3 for Bedrock integration
# =============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Install Python dependencies (pre-built wheels only)
RUN pip install --no-cache-dir --only-binary=:all: \
    'numpy==1.26.4' \
    'boto3==1.34.0'

# Copy shared utilities
COPY shared/ /var/task/shared/

# Copy Lambda handler
COPY lambdas/insight_generator/handler.py /var/task/handler.py

# Set the handler
CMD ["handler.lambda_handler"]