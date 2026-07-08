#!/usr/bin/env bash
# deploy.sh — Build and deploy AEREO Lambda to AWS
# Usage: ./deploy.sh --stack-name <name> --region <region> --ecr-repo <repo> --s3-bucket <bucket>
#
# Required arguments:
#   --stack-name     Name of the CloudFormation stack
#   --region         AWS Region to deploy to
#   --ecr-repo       Name of the ECR repository
#   --s3-bucket      Name of the S3 bucket for task staging (must be globally unique)
#
# Optional arguments:
#   --lambda-name    Name of the Lambda function (default: aereo-extractor)
#   --image-tag      Docker image tag (default: latest)
#   --dockerfile     Dockerfile to use (default: Dockerfile)

set -euo pipefail

STACK_NAME=""
REGION=""
ECR_REPO=""
S3_BUCKET=""
LAMBDA_NAME="aereo-extractor"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --stack-name) STACK_NAME="$2"; shift ;;
        --region) REGION="$2"; shift ;;
        --ecr-repo) ECR_REPO="$2"; shift ;;
        --s3-bucket) S3_BUCKET="$2"; shift ;;
        --lambda-name) LAMBDA_NAME="$2"; shift ;;
        --image-tag) IMAGE_TAG="$2"; shift ;;
        --dockerfile) DOCKERFILE="$2"; shift ;;
        -h|--help)
            grep "^#" "$0" | cut -c 3-
            exit 0
            ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

if [[ -z "$STACK_NAME" ]]; then echo "Error: --stack-name is required"; exit 1; fi
if [[ -z "$REGION" ]]; then echo "Error: --region is required"; exit 1; fi
if [[ -z "$ECR_REPO" ]]; then echo "Error: --ecr-repo is required"; exit 1; fi
if [[ -z "$S3_BUCKET" ]]; then echo "Error: --s3-bucket is required"; exit 1; fi

# Validate AWS credentials before doing anything.
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo "ERROR: AWS credentials not configured or invalid."
    echo "Run 'aws configure' and ensure 'aws sts get-caller-identity' works."
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"

echo "========================================"
echo "AEREO Lambda Deploy"
echo "========================================"
echo "Stack:      ${STACK_NAME}"
echo "Region:     ${REGION}"
echo "ECR:        ${ECR_URI}"
echo "S3 Bucket:  ${S3_BUCKET}"
echo "Dockerfile: ${DOCKERFILE}"
echo "========================================"

# ---------------------------------------------------------------------------
# 1. Ensure S3 bucket exists
# ---------------------------------------------------------------------------
echo ""
echo "[1/6] Checking S3 bucket..."
if ! aws s3api head-bucket --bucket "${S3_BUCKET}" 2>/dev/null; then
    echo "Creating S3 bucket: ${S3_BUCKET}"
    aws s3api create-bucket \
        --bucket "${S3_BUCKET}" \
        --region "${REGION}" \
        $( [ "${REGION}" != "us-east-1" ] && echo "--create-bucket-configuration LocationConstraint=${REGION}" )
    aws s3api put-bucket-versioning \
        --bucket "${S3_BUCKET}" \
        --versioning-configuration Status=Enabled
else
    echo "Bucket ${S3_BUCKET} already exists."
fi

# ---------------------------------------------------------------------------
# 2. Create ECR repository
# ---------------------------------------------------------------------------
echo ""
echo "[2/6] Checking ECR repository..."
if !     aws ecr describe-repositories --repository-names "${ECR_REPO}" --region "${REGION}" >/dev/null 2>&1; then
    echo "Creating ECR repository: ${ECR_REPO}"
    aws ecr create-repository --repository-name "${ECR_REPO}" --region "${REGION}"
else
    echo "ECR repository ${ECR_REPO} already exists."
fi

# ---------------------------------------------------------------------------
# 3. Login to ECR
# ---------------------------------------------------------------------------
echo ""
echo "[3/6] Logging in to ECR..."
aws ecr get-login-password --region "${REGION}" | \
    docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# ---------------------------------------------------------------------------
# 4. Build and push image
# ---------------------------------------------------------------------------
echo ""
echo "[4/6] Building Docker image using ${DOCKERFILE}..."
cd "$(dirname "$0")/../../.." || exit 1  # go to /root/repos
DOCKER_BUILDKIT=1 docker buildx build --load --provenance=false -f "aereo/projects/aereo-lambda/${DOCKERFILE}" -t "aereo-lambda:${IMAGE_TAG}" .

echo ""
echo "Tagging and pushing image..."
docker tag "aereo-lambda:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"

# ---------------------------------------------------------------------------
# 5. Deploy CloudFormation stack
# ---------------------------------------------------------------------------
echo ""
echo "[5/6] Deploying CloudFormation stack..."
aws cloudformation deploy \
    --stack-name "${STACK_NAME}" \
    --template-file "aereo/projects/aereo-lambda/infrastructure.yaml" \
    --region "${REGION}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        ImageUri="${ECR_URI}:${IMAGE_TAG}" \
        S3BucketName="${S3_BUCKET}" \
        LambdaFunctionName="${LAMBDA_NAME}"

# ---------------------------------------------------------------------------
# 6. Get outputs
# ---------------------------------------------------------------------------
echo ""
echo "[6/6] Getting stack outputs..."
aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
    --output table

echo ""
echo "========================================"
echo "DEPLOYMENT COMPLETE"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Test with: aws lambda invoke --function-name ${LAMBDA_NAME} --payload '{}' response.json"
echo "  2. Update your Python code to use:"
echo "       LambdaBackend('${LAMBDA_NAME}', S3Staging(bucket='${S3_BUCKET}'))"
echo ""
