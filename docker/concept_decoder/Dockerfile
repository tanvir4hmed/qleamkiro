# =============================================================================
# Concept Decoder Lambda - Docker Image
# Per-session concept graph lookup and proto-word crystallization check
# =============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Install Python dependencies (pre-built wheels only)
RUN pip install --no-cache-dir --only-binary=:all: \
    'boto3==1.34.0'

# Copy shared utilities
COPY shared/ /var/task/shared/

# Copy Lambda handler
COPY lambdas/concept_decoder/handler.py /var/task/handler.py

# Set the handler
CMD ["handler.lambda_handler"]
