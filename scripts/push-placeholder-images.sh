#!/bin/bash
# =============================================================================
# Push placeholder images to ECR for Lambda functions that don't have them yet
# Run this script to fix the "Source image does not exist" Terraform error
# =============================================================================

set -e

AWS_REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Lambda functions that may need placeholder images during first deploy.
# Keep this list in sync with infrastructure/modules/ecr/variables.tf.
MISSING_FUNCTIONS=(
    "feature_extraction"
    "cluster_engine"
    "reinforcement_engine"
    "insight_generator"
    "feedback_processor"
    "api_handler"
)

echo "🔧 Pushing placeholder images to ECR..."
echo "   Registry: $ECR_REGISTRY"
echo ""

# Login to ECR
echo "📡 Logging in to ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY

# Pull base image once
echo "📦 Pulling base Lambda image..."
docker pull public.ecr.aws/lambda/python:3.11

for FUNC in "${MISSING_FUNCTIONS[@]}"; do
    REPO_NAME="qleam-dev-${FUNC}"
    LAMBDA_NAME="qleam-dev-${FUNC//_/-}"
    
    # Check if Lambda function already exists
    if aws lambda get-function --function-name "$LAMBDA_NAME" --region $AWS_REGION 2>/dev/null; then
        echo "  ✅ $LAMBDA_NAME already exists — skipping"
        continue
    fi
    
    echo "  → Pushing placeholder to $REPO_NAME..."
    
    # Create temporary directory for placeholder
    TEMP_DIR=$(mktemp -d)
    
    # Create placeholder handler
    cat > "$TEMP_DIR/handler.py" << 'EOF'
def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "body": "Placeholder - run lambda-deploy workflow to update with actual code"
    }
EOF
    
    # Create Dockerfile
    cat > "$TEMP_DIR/Dockerfile" << 'EOF'
FROM public.ecr.aws/lambda/python:3.11
COPY handler.py /var/task/
CMD ["handler.lambda_handler"]
EOF
    
    # Build and push
    docker build -t "$ECR_REGISTRY/$REPO_NAME:latest" "$TEMP_DIR"
    docker push "$ECR_REGISTRY/$REPO_NAME:latest"
    
    # Cleanup
    rm -rf "$TEMP_DIR"
    
    echo "  ✅ Placeholder pushed to $REPO_NAME"
done

echo ""
echo "══════════════════════════════════════════════════════"
echo "✅ Done! You can now re-run your Terraform apply."
echo "══════════════════════════════════════════════════════"
