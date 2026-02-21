# =============================================================================
# API Handler Lambda - Docker Image
# Main API routing function
# =============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Install Python dependencies
RUN pip install --no-cache-dir \
    'boto3>=1.28.0'

# Copy shared utilities
COPY shared/ /var/task/shared/

# Copy Lambda handler
COPY lambdas/api_handler/handler.py /var/task/handler.py

# Set the handler
CMD ["handler.lambda_handler"]