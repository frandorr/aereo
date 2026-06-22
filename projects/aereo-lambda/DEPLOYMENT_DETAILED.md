# AEREO Lambda: Detailed AWS Deployment Guide

> **Security notice:** This guide provides a working example that prioritizes getting the Lambda running end-to-end. The default IAM permissions shown are intentionally broad so the deployment script can create and manage every required resource. Before using this in a production account, restrict the IAM scope to the minimum required actions and resources, enable S3 encryption, block public S3 access, rotate credentials regularly, and avoid long-lived access keys whenever possible.

This guide documents the exact steps, IAM configuration, and authentication setup required to deploy the AEREO Lambda function to AWS and run the Sentinel-2 serverless example end-to-end.

## Table of Contents

1. [What This Guide Covers](#what-this-guide-covers)
2. [Architecture & Resource Overview](#architecture--resource-overview)
3. [Cost and Service Quota Warning](#cost-and-service-quota-warning)
4. [Prerequisites](#prerequisites)
5. [IAM Permissions](#iam-permissions)
6. [Authentication Setup](#authentication-setup)
7. [Deployment Steps](#deployment-steps)
8. [Verification](#verification)
9. [Running the Sentinel-2 Example](#running-the-sentinel-2-example)
10. [Troubleshooting](#troubleshooting)
11. [Updating After Code Changes](#updating-after-code-changes)
12. [Teardown](#teardown)
13. [Files Reference](#files-reference)

---

## What This Guide Covers

By the end of this guide you will have:

- An ECR repository containing a container image for the AEREO Lambda.
- An S3 bucket used for task staging and extraction results.
- A CloudFormation stack with an IAM execution role and a Lambda function named `aereo-extractor`.
- A working run of `examples/serverless/lambda_sentinel2_extraction.py` against the deployed Lambda.

The deployment uses the **production Dockerfile** (`projects/aereo-lambda/Dockerfile`), which builds AEREO core from the local monorepo and installs pipeline plugins as needed. The Sentinel-2 example uses only built-in plugins (`aereo.builtins`), so no additional PyPI plugin installation is required.

---

## Architecture & Resource Overview

```text
                              ┌─────────────────┐
                              │   Event JSON    │
                              │   (task_uri)    │
                              └────────┬────────┘
                                       │
                                       ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   S3 Upload     │     │  Lambda Function │     │   S3 Download   │
│ (task assets    │────▶│  aereo-extractor │────▶│ (task assets    │
│  + task_meta)   │     │                 │     │  + task_meta)   │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │  ExtractConfig   │
                        │  Pipeline        │
                        │  (TaskRunner)    │
                        └────────┬─────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │   GeoDataFrame   │
                        │  [ArtifactSchema]│
                        └────────┬─────────┘
                                 │
                                 ▼
┌─────────────────┐     ┌──────────────────┐
│  Response JSON  │◄────│   S3 Upload      │
│ (manifest_uri)  │     │ (GeoTIFFs +      │
│                 │     │  artifacts)      │
└─────────────────┘     └──────────────────┘
```

| Resource | Purpose |
|----------|---------|
| AWS Account | Account that owns all resources. |
| IAM deployment user | Human or CI user that runs `deploy.sh`. |
| AWS Region | Region for all resources. |
| CloudFormation stack | Top-level stack grouping the Lambda and role. |
| ECR repository | Stores the Docker image. |
| S3 bucket | Task staging (`aereo-tasks/`) and results (`results/`). |
| Lambda function | Container-image Lambda that executes `ExtractionTask`s. |
| Lambda architecture | Must match the Docker image architecture (`arm64` or `x86_64`). |

The Lambda is invoked asynchronously by `LambdaBackend` in the Python client. For each task:

1. The client uploads task metadata and assets to S3 under `s3://<bucket>/aereo-tasks/<job_id>/<chunk_id>/`.
2. The client invokes the Lambda with the S3 prefix.
3. The Lambda downloads the task, runs the extraction pipeline, writes GeoTIFFs to `/tmp`, and uploads results to `s3://<bucket>/results/<job_id>/<chunk_id>/`.
4. The Lambda returns a JSON response containing the S3 URI of the result manifest.

---

## Cost and Service Quota Warning

Deploying this example creates billable resources:

- **Lambda**: 3008 MB memory, 900 second timeout, container image ~several GB. Each invocation is billed for memory and duration.
- **ECR**: Storage for the container image plus data transfer for pulls.
- **S3**: Storage for staged tasks and results, plus request and data-transfer charges.
- **CloudWatch Logs**: Log ingestion and storage charges.

The Sentinel-2 example in this guide downloads public Sentinel-2 data and may transfer several GB. Verify that your AWS account has the required service quotas (especially Lambda concurrent executions and ECR storage) and set up billing alerts before running large jobs.

---

## Prerequisites

### 1. Local Machine / Environment

You need a Linux or macOS machine with:

- `git`
- `uv` (Python package manager): <https://docs.astral.sh/uv/getting-started/installation/>
- Docker with `buildx` support
- AWS CLI v2
- Sufficient disk space for the Docker build (at least 8 GB free)

**Important:** The Lambda architecture must match the architecture of the Docker image you build.

| Build machine | Lambda architecture | Notes |
|---------------|---------------------|-------|
| ARM64 (Apple Silicon, Graviton) | `arm64` | Default in this guide. |
| x86_64 | `x86_64` | Build with `docker buildx build --platform linux/amd64 ...`. |

Cross-compiling x86_64 on an ARM64 host under QEMU is unreliable for this image, so use `arm64` when building on ARM64.

### 2. AWS Account

You need an active AWS account with permission to create IAM users, ECR repositories, S3 buckets, CloudFormation stacks, and Lambda functions.

### 3. Repository Layout

The AEREO monorepo is expected to be cloned at a path such that the **parent directory** of the repository is the Docker build context. In the examples below the repository is at `/root/repos/aereo`, but any path works as long as the parent directory is used as the build context.

```text
/root/repos/              # Docker build context (parent of the repo)
└── aereo/                # this repository
    ├── bases/
    ├── components/
    ├── projects/
    │   └── aereo-lambda/
    │       ├── deploy.sh
    │       ├── Dockerfile
    │       └── infrastructure.yaml
    └── examples/
        └── serverless/
            └── lambda_sentinel2_extraction.py
```

The Dockerfile copies paths like `aereo/pyproject.toml`, `aereo/components/`, etc., so the build context **must** be the parent directory (e.g., `/root/repos`), not the repository root (`/root/repos/aereo`).

---

## IAM Permissions

### Deployment User Permissions

The `aereo-deploy` user needs permissions to create and manage ECR, S3, CloudFormation, Lambda, and IAM resources. The fastest path for a first-time deployment is to attach the managed policies listed below.

> **These permissions are intentionally broad and are shown only as a working example.** For any non-experimental account, replace them with the least-privilege inline policy in the next subsection.

| Managed Policy | Why It Is Needed |
|----------------|------------------|
| `AmazonEC2ContainerRegistryFullAccess` | Create ECR repo, push/pull images. |
| `AWSLambda_FullAccess` | Create and update the Lambda function. |
| `AmazonS3FullAccess` | Create the S3 bucket and manage objects. |
| `AWSCloudFormationFullAccess` | Create/update/delete the CloudFormation stack. |
| `IAMFullAccess` | Create the Lambda execution role and its policies. |

To attach them via AWS CLI:

```bash
aws iam attach-user-policy --user-name aereo-deploy --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess
aws iam attach-user-policy --user-name aereo-deploy --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess
aws iam attach-user-policy --user-name aereo-deploy --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-user-policy --user-name aereo-deploy --policy-arn arn:aws:iam::aws:policy/AWSCloudFormationFullAccess
aws iam attach-user-policy --user-name aereo-deploy --policy-arn arn:aws:iam::aws:policy/IAMFullAccess
```

#### Least-Privilege Alternative (Recommended for Production)

For a scoped inline policy, replace the placeholders (`<region>`, `<account-id>`, `<your-bucket>`, `<stack-name>`, `<function-name>`, `<ecr-repo-name>`) with your values:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ECRAccess",
            "Effect": "Allow",
            "Action": [
                "ecr:GetAuthorizationToken"
            ],
            "Resource": "*"
        },
        {
            "Sid": "ECRRepoAccess",
            "Effect": "Allow",
            "Action": [
                "ecr:CreateRepository",
                "ecr:DescribeRepositories",
                "ecr:InitiateLayerUpload",
                "ecr:UploadLayerPart",
                "ecr:CompleteLayerUpload",
                "ecr:PutImage",
                "ecr:BatchCheckLayerAvailability"
            ],
            "Resource": "arn:aws:ecr:<region>:<account-id>:repository/<ecr-repo-name>"
        },
        {
            "Sid": "S3Access",
            "Effect": "Allow",
            "Action": [
                "s3:CreateBucket",
                "s3:PutBucketVersioning",
                "s3:PutBucketPublicAccessBlock",
                "s3:PutEncryptionConfiguration",
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::<your-bucket>",
                "arn:aws:s3:::<your-bucket>/*"
            ]
        },
        {
            "Sid": "CloudFormationAccess",
            "Effect": "Allow",
            "Action": [
                "cloudformation:CreateChangeSet",
                "cloudformation:CreateStack",
                "cloudformation:DeleteStack",
                "cloudformation:DescribeStacks",
                "cloudformation:ExecuteChangeSet",
                "cloudformation:GetTemplateSummary",
                "cloudformation:SetStackPolicy",
                "cloudformation:UpdateStack"
            ],
            "Resource": [
                "arn:aws:cloudformation:<region>:<account-id>:stack/<stack-name>/*",
                "arn:aws:cloudformation:<region>:<account-id>:stackset/*:*"
            ]
        },
        {
            "Sid": "LambdaAccess",
            "Effect": "Allow",
            "Action": [
                "lambda:CreateFunction",
                "lambda:UpdateFunctionCode",
                "lambda:UpdateFunctionConfiguration",
                "lambda:GetFunction",
                "lambda:InvokeFunction"
            ],
            "Resource": "arn:aws:lambda:<region>:<account-id>:function:<function-name>"
        },
        {
            "Sid": "IAMAccess",
            "Effect": "Allow",
            "Action": [
                "iam:CreateRole",
                "iam:GetRole",
                "iam:AttachRolePolicy",
                "iam:PutRolePolicy",
                "iam:PassRole",
                "iam:DeleteRole",
                "iam:DeleteRolePolicy",
                "iam:DetachRolePolicy",
                "iam:GetRolePolicy",
                "iam:ListRolePolicies",
                "iam:ListAttachedRolePolicies"
            ],
            "Resource": "arn:aws:iam::<account-id>:role/<function-name>-execution-role"
        },
        {
            "Sid": "STSAccess",
            "Effect": "Allow",
            "Action": "sts:GetCallerIdentity",
            "Resource": "*"
        }
    ]
}
```

### Lambda Execution Role

The CloudFormation template (`infrastructure.yaml`) creates an IAM role for the Lambda function. You do **not** create this manually. The role is:

- Name: `<function-name>-execution-role` (e.g., `aereo-extractor-execution-role`)
- Trust policy: allows `lambda.amazonaws.com` to assume it.
- Managed policy: `AWSLambdaBasicExecutionRole` (CloudWatch Logs).
- Inline policy: `S3TaskAccess`, granting `s3:GetObject`, `s3:PutObject`, and `s3:ListBucket` on the staging/results bucket.

The role has no permissions outside the specified S3 bucket. If the extraction pipeline reads from **other** S3 buckets (e.g., public Sentinel-2 data in a different region), the Lambda may need additional permissions or the public bucket must allow anonymous access.

---

## Authentication Setup

### Step 1: Create the Deployment IAM User

1. Sign in to the AWS Management Console.
2. Go to **IAM → Users → Create user**.
3. Choose a user name, e.g., `aereo-deploy`.
4. Select **Attach policies directly**.
5. Attach the policies listed in the [IAM Permissions](#iam-permissions) section above.
6. After creating the user, open it and go to **Security credentials → Create access key**.
7. Choose **Command Line Interface (CLI)**, confirm the warning, and save the **Access key ID** and **Secret access key**.

> Store the access key securely. Do not commit it to the repository. For CI/CD, prefer an IAM role with OIDC federation instead of long-lived access keys.

### Step 2: Configure the AWS CLI

On the deployment machine:

```bash
aws configure
```

Enter:

```text
AWS Access Key ID [None]: <Access key ID for aereo-deploy>
AWS Secret Access Key [None]: <Secret access key for aereo-deploy>
Default region name [None]: <your-region>
Default output format [None]: json
```

If you use multiple AWS CLI profiles, specify the profile when running commands:

```bash
export AWS_PROFILE=aereo-deploy
```

Verify the credentials:

```bash
aws sts get-caller-identity
```

Expected output format:

```json
{
    "UserId": "AIDA...",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/aereo-deploy"
}
```

`deploy.sh` also runs this check internally and aborts if credentials are missing.

### Step 3: Docker Login to ECR

`deploy.sh` performs this automatically, but you can also do it manually:

```bash
REGION=<your-region>
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr get-login-password --region "${REGION}" | \
    docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
```

---

## Deployment Steps

### Step 1: Clone and Enter the Repository

```bash
cd /root/repos
git clone <aereo-repository-url> aereo
cd aereo
```

### Step 2: Decide on Names

Choose values for:

| Variable | Example Value | Notes |
|----------|---------------|-------|
| `STACK_NAME` | `aereo-stack` | Must be unique per region. Can be reused for updates. |
| `REGION` | `us-east-1` | Must match your AWS CLI default region. |
| `ECR_REPO` | `aereo-lambda` | ECR repository name; created if missing. |
| `S3_BUCKET` | `aereo-tasks-<account-id>` | Must be globally unique, DNS-compatible, no underscores. |
| `FUNCTION_NAME` | `aereo-extractor` | Hard-coded in `infrastructure.yaml` via `LambdaFunctionName` parameter default. |

The Lambda function name defaults to `aereo-extractor` in the CloudFormation template. If you need a different name, edit `infrastructure.yaml` or pass `LambdaFunctionName=...` in `deploy.sh`.

### Step 3: Review the Dockerfile

Open `projects/aereo-lambda/Dockerfile` and confirm:

- It installs the `expat` system library (required by GDAL/rasterio).
- It builds the `aereo` core wheel and the `aereo-lambda` project wheel.
- If you need real pipeline plugins from PyPI, uncomment the `pip install` lines.

The Sentinel-2 example uses only built-ins (`SearchSTAC`, `ReadODCSTAC`, `ReprojectODC`, `WriteGeoTIFF`), so no extra plugins are required. For other data sources you may need additional plugins:

| Data source | Reader plugin example | Notes |
|-------------|----------------------|-------|
| Sentinel-2 (STAC/ODC) | Built-in `ReadODCSTAC` | Used in this guide. |
| GOES ABI (satpy) | `aereo-extract-satpy` | Install from PyPI or local source. |

### Step 4: Review the CloudFormation Template

Open `projects/aereo-lambda/infrastructure.yaml` and confirm:

```yaml
AereoLambdaFunction:
  Type: AWS::Lambda::Function
  Properties:
    FunctionName: !Ref LambdaFunctionName
    PackageType: Image
    Architectures:
      - arm64
    ...
```

`Architectures` must match the architecture of the Docker image you are about to build. If your build machine is ARM64 (Apple Silicon, Graviton), use `arm64`. If your build machine is x86_64 and you do not want cross-compilation, use `x86_64`.

### Step 5: Run the Deployment Script

```bash
cd /root/repos/aereo/projects/aereo-lambda
./deploy.sh <STACK_NAME> <REGION> <ECR_REPO> <S3_BUCKET>
```

Example:

```bash
./deploy.sh aereo-stack us-east-1 aereo-lambda aereo-tasks-123456789012
```

> Replace `123456789012` with your AWS account ID so the S3 bucket name is globally unique.

The script performs these steps:

1. Validates AWS credentials via `aws sts get-caller-identity`.
2. Creates the S3 bucket if it does not exist (with versioning enabled).
3. Creates the ECR repository if it does not exist.
4. Logs Docker into ECR.
5. Builds the Docker image from the repository parent directory (`/root/repos`).
6. Tags the image as `<account-id>.dkr.ecr.<region>.amazonaws.com/<repo>:latest` and pushes it.
7. Deploys the CloudFormation stack.
8. Prints stack outputs (Lambda ARN, function name, bucket name).

> **Image tagging:** The script pushes a `:latest` tag for simplicity. For reproducibility and easier rollbacks, consider tagging each build with a Git commit hash or timestamp and updating the Lambda to use that tag instead of `:latest`.

Successful output ends with a table similar to:

```text
+--------------------+----------------------------------------------------------------+
|  LambdaFunctionArn |  arn:aws:lambda:<region>:<account-id>:function:aereo-extractor |
|  LambdaFunctionName|  aereo-extractor                                               |
|  S3BucketName      |  <your-bucket>                                                |
+--------------------+----------------------------------------------------------------+
```

### Step 6: Verify the Lambda Function

In the AWS Console, go to **Lambda → Functions → aereo-extractor** and confirm:

- Runtime: `Container image`
- Architecture: `arm64` (or `x86_64`, matching your build)
- Memory: 3008 MB
- Timeout: 900 seconds
- Image URI points to your ECR repo.

### Step 7: Recommended Security Hardening

After the stack is created, apply the following settings to the S3 bucket:

1. Block all public access:

```bash
aws s3api put-public-access-block \
  --bucket <your-bucket> \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

2. Enable default server-side encryption:

```bash
aws s3api put-bucket-encryption \
  --bucket <your-bucket> \
  --server-side-encryption-configuration \
  '{"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}'
```

3. (Optional) Place the Lambda in a VPC only if it needs access to private resources. By default the Lambda has outbound internet access through AWS Lambda's managed infrastructure, which is required for public data sources such as Sentinel-2 STAC catalogs.

---

## Verification

### Test 1: Simple CLI Invocation

Use a minimal valid payload to confirm the Lambda starts and can read from S3:

```bash
aws lambda invoke \
  --function-name aereo-extractor \
  --region <your-region> \
  --cli-binary-format raw-in-base64-out \
  --payload '{"task_uri": "s3://<your-bucket>/aereo-tasks/test/0/", "output_prefix": "s3://<your-bucket>/results/test/0/", "job_id": "test", "chunk_id": 0}' \
  response.json

cat response.json
```

If the S3 prefix does not contain a valid staged task, the handler will return an error, but the invocation should still produce CloudWatch logs. Use this only to confirm the container starts.

### Test 2: Check CloudWatch Logs

```bash
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/aereo-extractor --region <your-region>
```

After invocation, logs appear under `/aws/lambda/aereo-extractor`.

### Test 3: Run the Full Sentinel-2 Example

See the next section.

---

## Running the Sentinel-2 Example

The example at `examples/serverless/lambda_sentinel2_extraction.py` mirrors `examples/01-sentinel2.ipynb` but routes extraction through `LambdaBackend`.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AEREO_S3_BUCKET` | `aereo-tasks` | S3 bucket for staging and results. |
| `AEREO_LAMBDA_FUNCTION` | `aereo-extractor` | Lambda function name. |
| `AWS_ENDPOINT_URL` | unset | Set only for LocalStack/MinIO. Must be empty for real AWS. |
| `LAMBDA_URL` | unset | Set only for local RIE testing. |

For real AWS, run:

```bash
cd /root/repos/aereo
AEREO_S3_BUCKET=<your-bucket> \
AEREO_LAMBDA_FUNCTION=aereo-extractor \
uv run python examples/serverless/lambda_sentinel2_extraction.py
```

### Expected Output

```text
Searching for Sentinel-2 L2A assets...
Found 16 asset rows

Preparing extraction tasks...
Prepared 8 task(s)

Executing 8 task(s) via Lambda 'aereo-extractor'...
Extracted 38 artifact(s)

Result columns: ['id', 'source_ids', 'start_time', 'end_time', 'uri', 'collection', 'geometry', 'grid_cell', 'grid_dist', 'cell_geometry', 'cell_utm_crs', 'cell_utm_footprint']

Artifacts stored in S3 bucket: s3://<your-bucket>/results/
```

### Inspecting Results in S3

```bash
aws s3 ls s3://<your-bucket>/results/ --recursive --region <your-region>
```

You will see:

```text
results/<job-id>/<chunk-id>/artifacts.parquet
results/<job-id>/<chunk-id>/manifest.json
results/<job-id>/<chunk-id>/<id>.tif
```

---

## Troubleshooting

### `Runtime.InvalidEntrypoint`

- Cause: Lambda architecture does not match image architecture.
- Fix: Align `Architectures` in `infrastructure.yaml` with the image architecture.

### `Cannot connect to the Docker daemon`

- Cause: Docker is not running or the user lacks permissions.
- Fix: Start Docker and add your user to the `docker` group, or run with `sudo`.

### `An error occurred (BucketAlreadyExists)`

- Cause: S3 bucket names are globally unique.
- Fix: Choose a different bucket name, e.g., `aereo-tasks-<your-account-id>`.

### `No changes to deploy`

- Cause: Only the Docker image changed, not the CloudFormation template.
- Fix: The Lambda function code is still updated because the image digest changes. If it is not, manually update:

```bash
aws lambda update-function-code \
  --function-name aereo-extractor \
  --image-uri $(aws sts get-caller-identity --query Account --output text).dkr.ecr.<your-region>.amazonaws.com/<your-ecr-repo>:latest \
  --region <your-region>
```

### `Read-only file system: '/var/task/...'`

- Cause: The writer tried to write outside `/tmp`.
- Fix: Ensure the job's `output_uri` is under `/tmp`.

### `ImportError: libexpat.so.1`

- Cause: The `expat` system library is missing from the image.
- Fix: Confirm `microdnf install -y expat` is present in the Dockerfile and rebuild.

### No GeoTIFFs in S3, only `artifacts.parquet`

- Cause: The handler did not upload the local GeoTIFF files.
- Fix: Check `aereo/bases/aereo/lambda_handler/core.py`; the handler should iterate over artifact rows and upload each `uri` that exists on disk.

---

## Updating After Code Changes

To deploy a new version of the code, rerun `deploy.sh` with the same arguments:

```bash
cd /root/repos/aereo/projects/aereo-lambda
./deploy.sh <STACK_NAME> <REGION> <ECR_REPO> <S3_BUCKET>
```

The script will:

1. Rebuild the image with your current code.
2. Push a new image digest to ECR.
3. Update the CloudFormation stack, which updates the Lambda function code.

If you only changed application code (not the template), CloudFormation may report `No changes to deploy`, but the Lambda image URI changes because the digest changes, so the function is still updated.

To roll back to the previous image quickly:

```bash
aws lambda update-function-code \
  --function-name aereo-extractor \
  --image-uri <previous-image-uri> \
  --region <your-region>
```

---

## Teardown

To remove all resources created by this guide, run the commands below. Replace placeholders with your actual values.

```bash
STACK_NAME=aereo-stack
REGION=us-east-1
S3_BUCKET=aereo-tasks-<account-id>
ECR_REPO=aereo-lambda
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Empty and delete the S3 bucket
aws s3 rm s3://${S3_BUCKET} --recursive --region ${REGION}
aws s3 rb s3://${S3_BUCKET} --region ${REGION}

# Delete the CloudFormation stack
aws cloudformation delete-stack --stack-name ${STACK_NAME} --region ${REGION}
aws cloudformation wait stack-delete-complete --stack-name ${STACK_NAME} --region ${REGION}

# Delete the ECR repository and its images
aws ecr delete-repository --repository-name ${ECR_REPO} --force --region ${REGION}
```

> Deleting the stack removes the Lambda function and IAM role. Deleting the ECR repository removes all image versions.

---

## Files Reference

| File | Description |
|------|-------------|
| `projects/aereo-lambda/deploy.sh` | One-command deployment orchestration. |
| `projects/aereo-lambda/infrastructure.yaml` | CloudFormation template (IAM role + Lambda). |
| `projects/aereo-lambda/Dockerfile` | Production container image build. |
| `projects/aereo-lambda/Dockerfile.local` | Local development image with optional local plugins. |
| `projects/aereo-lambda/docker-compose.yml` | LocalStack + Lambda RIE for local testing. |
| `projects/aereo-lambda/test_local_lambda.py` | Local integration test against LocalStack/RIE. |
| `examples/serverless/lambda_sentinel2_extraction.py` | End-to-end AWS example used for verification. |
