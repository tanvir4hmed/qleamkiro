# =============================================================================
# Base Dockerfile for Qleam Lambda Functions
# AWS Lambda Python 3.11 runtime with shared utilities
# =============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Install system dependencies for audio processing
RUN yum install -y -q libsndfile && \
    yum clean all

# Copy shared utilities
COPY shared/ /var/task/shared/

# Set working directory
WORKDIR /var/task

# Default handler (will be overridden by specific Dockerfiles)
CMD ["handler.lambda_handler"]