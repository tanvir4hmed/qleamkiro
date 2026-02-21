# =============================================================================
# Base Dockerfile for Qleam Lambda Functions
# AWS Lambda Python 3.11 runtime with shared utilities
# =============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Install system dependencies for audio processing
# Support both yum (AL2) and dnf (AL2023) so base image updates don't break the build
RUN set -e; \
    if command -v dnf >/dev/null 2>&1; then dnf install -y -q libsndfile && dnf clean all; \
    else yum install -y -q libsndfile && yum clean all; fi

# Copy shared utilities
COPY shared/ /var/task/shared/

# Set working directory
WORKDIR /var/task

# Default handler (will be overridden by specific Dockerfiles)
CMD ["handler.lambda_handler"]