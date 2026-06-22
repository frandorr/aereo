# AEREO Lambda AWS Deployment Guide

This guide walks you through deploying the AEREO Lambda function to AWS with the pipeline plugins you need for your data source.

> **Architecture note:** AEREO now uses a stage-based pipeline (`Reader` → `Reprojector` → `Writer`) configured through `ExtractConfig`. The Lambda handler receives a fully instantiated `ExtractionTask` and executes it with `TaskRunner`; no runtime plugin registry is required inside the container. Older single-class "extractor" plugins are no longer used.

## Overview

The deployment process:
1. Creates an S3 bucket for task staging
2. Creates an ECR repository for the Docker image
3. Builds a Docker image with AEREO core + the pipeline plugins you need (reader, reprojector, writer)
4. Pushes the image to ECR
5. Deploys a CloudFormation stack with IAM role + Lambda function

## Prerequisites

### 1. AWS Account
- You need an active AWS account
- Default region: `us-west-2` (configurable)

### 2. Create an IAM User for Deployment

1. Open [AWS Console](https://console.aws.amazon.com/)
2. Navigate to **IAM** → **Users** → **Create user**
3. User name: `aereo-deploy`
4. Attach these policies:
   - `AmazonEC2ContainerRegistryFullAccess` (ECR)
   - `AWSLambda_FullAccess` (Lambda)
   - `AmazonS3FullAccess` (S3)
   - `AWSCloudFormationFullAccess` (CloudFormation)
   - `IAMFullAccess` (IAM roles)
5. Go to the user → **Security credentials** → **Create access key**
6. Save the **Access Key ID** and **Secret Access Key**

### 3. Install AWS CLI

```bash
# On Debian/Ubuntu
apt-get update && apt-get install -y awscli

# Or install official AWS CLI v2
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install --update
```

### 4. Configure AWS Credentials

```bash
aws configure
# Enter:
# - Access Key ID: YOUR_ACCESS_KEY
# - Secret Access Key: YOUR_SECRET_KEY
# - Default region: us-west-2
# - Output format: json
```

Verify it works:
```bash
aws sts get-caller-identity
```

## Deployment

### Quick Deploy (One Command)

```bash
cd /root/repos/aereo/projects/aereo-lambda
./deploy.sh <STACK_NAME> <REGION> <ECR_REPO> <S3_BUCKET>
```

**Example:**
```bash
./deploy.sh ikd us-west-2 ikd frandorr-lambda-tests
```

Parameters:
- `STACK_NAME`: CloudFormation stack name (e.g., `ikd`)
- `REGION`: AWS region (e.g., `us-west-2`)
- `ECR_REPO`: ECR repository name (e.g., `ikd`)
- `S3_BUCKET`: S3 bucket name for task staging (must be globally unique, no underscores)

### What the Script Does

1. **Creates S3 bucket** (if it doesn't exist)
2. **Creates ECR repository** (if it doesn't exist)
3. **Logs Docker into ECR**
4. **Builds Docker image** using `Dockerfile.local` (includes all local plugins)
5. **Pushes image to ECR**
6. **Deploys CloudFormation stack** with:
   - IAM execution role (S3 read/write + CloudWatch logs)
   - Lambda function (container image, 3008MB RAM, 900s timeout)

## Dockerfile Variants

### Dockerfile.local (Testing with Local Plugins)

Use this for development - it copies and builds local plugin repos:

```dockerfile
# Build from /root/repos (parent of aereo/)
COPY aereo-extract-satpy/ plugins/aereo-extract-satpy/
COPY aereo-extract-odc-stac/ plugins/aereo-extract-odc-stac/
# ... etc
```

Build command:
```bash
cd /root/repos
docker build -f aereo/projects/aereo-lambda/Dockerfile.local -t aereo-lambda:local .
```

### Dockerfile (Production)

Use this for production - installs plugins from PyPI:

```dockerfile
# Uncomment to install real pipeline plugins from PyPI:
RUN pip install aereo-extract-satpy aereo-extract-odc-stac
```

## Verification

### Check Plugins Inside the Image

```bash
docker run --rm --entrypoint python aereo-lambda:local -c "
import importlib.metadata
for ep in importlib.metadata.entry_points(group='aereo.plugins'):
    print(f'{ep.name}: {ep.value}')
"
```
Expected output depends on which plugins are installed, but should include the built-ins and any extras you added:

```
process_composite: aereo.builtins.processor:Composite
process_ndvi: aereo.builtins.processor:NDVI
process_normalize: aereo.builtins.processor:Normalize
process_qa_mask: aereo.builtins.processor:QAMask
process_select_bands: aereo.builtins.processor:SelectBands
read_odc_stac: aereo.builtins.read:ReadODCSTAC
reproject_odc: aereo.builtins.reproject:ReprojectODC
search_stac: aereo.builtins.search:SearchSTAC
write_geotiff: aereo.builtins.write:WriteGeoTIFF
```

### Test Lambda Invocation

```bash
aws lambda invoke \
  --function-name aereo-extractor \
  --region us-west-2 \
  --payload '{"task_uri": "s3://frandorr-lambda-tests/test-task/", "output_prefix": "s3://frandorr-lambda-tests/results/test/", "job_id": "test", "chunk_id": 0}' \
  response.json

cat response.json
```

### Pipeline Plugin Recommendation

For GOES data extraction, configure an `ExtractConfig` with a satpy-based reader and the built-in `WriteGeoTIFF` writer. The old single-class `extract_satpy` / `extract_aws_goes` extractor plugins are no longer used.

## Full Working Example: Sentinel-2 Extraction via Lambda

See `examples/serverless/lambda_sentinel2_extraction.py`. It reproduces `examples/01-sentinel2.ipynb` end-to-end using `LambdaBackend` and stores GeoTIFF artifacts in S3.

## Legacy GOES-19 ABI Example

> **Outdated:** The example below uses the previous single-class extractor plugin API (`AereoProfile`, `prepare_for_extraction`, `plugin_hints`). It is left for reference but will not work with the current `ExtractConfig` / `AereoClient` API. For an up-to-date Lambda example, use the Sentinel-2 script above.

This example searches for GOES-19 ABI C02 data, prepares extraction tasks, and executes them via Lambda. Results (GeoTIFFs + metadata) are stored in S3.

Save this as `examples/serverless/lambda_goes_extraction.py`:

```python
#!/usr/bin/env python3
"""Lambda GOES Extraction Example — Search, extract, and store results in S3."""

from datetime import datetime, timezone

from aereo.client import AereoClient
from aereo.interfaces import AereoProfile, GridConfig
from aereo.backends import LambdaBackend
from aereo.backends.staging import CloudTaskStaging
from shapely.geometry import box

# ---------------------------------------------------------------------------
# 1. Define the extraction profile
# ---------------------------------------------------------------------------
profile = AereoProfile(
    name="goes",
    resolution=1000,
    collections={"ABI-L1b-RadF": ["C02"]},
    # Use extract_satpy (recommended) or extract_aws_goes
    plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
    search_params={"satellite": "GOES-19"},
    extract_params={
        "reader": "abi_l1b",
        "calibration": "reflectance",
        "delay_writes": True,
    },
)

# ---------------------------------------------------------------------------
# 2. Configure Lambda backend with S3 staging
# ---------------------------------------------------------------------------
BUCKET = "frandorr-lambda-tests"      # Your S3 bucket
FUNCTION_NAME = "aereo-extractor"     # Lambda function name
REGION = "us-west-2"                  # AWS region

staging = CloudTaskStaging(bucket=BUCKET)
lambda_backend = LambdaBackend(
    function_name=FUNCTION_NAME,
    staging=staging,
)

# ---------------------------------------------------------------------------
# 3. Create client with Lambda backend
# ---------------------------------------------------------------------------
client = AereoClient(
    profiles=[profile],
    grid_config=GridConfig(target_grid_dist=256_000),
    aoi=box(-70, -40, -68, -39),
    backend=lambda_backend,
)

# ---------------------------------------------------------------------------
# 4. Search for GOES data
# ---------------------------------------------------------------------------
print("Searching for GOES-19 ABI C02 data...")
results = client.search(
    start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 2, 14, 10, tzinfo=timezone.utc),
)
print(f"Found {len(results)} assets")

# ---------------------------------------------------------------------------
# 5. Prepare extraction tasks
# ---------------------------------------------------------------------------
print("Preparing extraction tasks...")
tasks = client.prepare_for_extraction(
    results,
    uri=f"s3://{BUCKET}/goes-results",
)
print(f"Prepared {len(tasks)} task(s)")

# ---------------------------------------------------------------------------
# 6. Execute tasks via Lambda
# ---------------------------------------------------------------------------
print(f"Executing {len(tasks)} task(s) via Lambda '{FUNCTION_NAME}'...")
results_df = client.execute_tasks(tasks)
print(f"Extraction complete! {len(results_df)} artifact(s) returned")

# ---------------------------------------------------------------------------
# 7. Inspect results
# ---------------------------------------------------------------------------
print("\nResults:")
print(results_df.head())

if len(results_df) > 0:
    print(f"\nArtifacts stored in S3 bucket: {BUCKET}")
    print("Result columns:", list(results_df.columns))

    # Save result metadata locally
    results_df.to_parquet("/tmp/lambda_goes_results.parquet")
    print("Saved result metadata to /tmp/lambda_goes_results.parquet")
else:
    print("No results returned.")

print("\nDone!")
```

### Run the Example

```bash
cd /root/repos/aereo
uv run python examples/serverless/lambda_goes_extraction.py
```

### Expected Output

```
Searching for GOES-19 ABI C02 data...
Found 1 assets
Preparing extraction tasks...
Prepared 1 task(s)
Executing 1 task(s) via Lambda 'aereo-extractor'...
Extraction complete! 2 artifact(s) returned

Results:
                                 id  ...                                 cell_utm_footprint
0  0f31fc0584587777991f788f7ed4fc6e  ...  POLYGON ((451244.46 5459675.858, ...
1  d36a5fc442d1e6f54e85914a299705e2  ...  POLYGON ((705629.478 5456957.212, ...

Artifacts stored in S3 bucket: frandorr-lambda-tests
Result columns: ['id', 'source_ids', 'start_time', 'end_time', 'uri', 'geometry', ...]
```

### S3 Output Structure

After successful execution, your S3 bucket will contain:

```
s3://frandorr-lambda-tests/
├── aereo-tasks/                    # Staged task files (temporary)
│   └── default/
│       └── 0/
│           ├── task_meta.json
│           └── task_assets.parquet
└── results/                        # Extraction outputs
    └── default/
        └── 0/
            ├── manifest.json                    # Points to artifacts.parquet
            ├── artifacts.parquet               # Metadata GeoDataFrame
            └── loc-18D23L_start-20260402T140020_...res-1000m.tif   # GeoTIFF #1
            └── loc-18D24L_start-20260402T140020_...res-1000m.tif   # GeoTIFF #2
```

Each `.tif` file is a GeoTIFF with proper CRS and georeferencing. The `artifacts.parquet` contains all metadata (geometry, timestamps, collection info) with `uri` pointing to the S3 location of each GeoTIFF.

### Using the Deployed Lambda in Your Own Code

```python
from aereo.backends import LambdaBackend
from aereo.backends.staging import CloudTaskStaging

backend = LambdaBackend(
    function_name="aereo-extractor",
    staging=CloudTaskStaging(bucket="frandorr-lambda-tests"),
)

# Run your extraction tasks
results = backend.run_tasks(tasks)
```

## CloudFormation Resources

The deployment creates:

| Resource | Purpose |
|----------|---------|
| **ECR Repository** | Stores the Docker image |
| **IAM Role** | Lambda execution role with S3 + CloudWatch access |
| **Lambda Function** | `aereo-extractor` running your container |
| **S3 Bucket** | Task staging and results storage |

## Troubleshooting

### "Bucket name is not valid"
S3 bucket names cannot contain underscores. Use hyphens instead:
- ❌ `lambda_tests`
- ✅ `lambda-tests`
- ✅ `frandorr-lambda-tests`

### "Bucket already exists"
S3 bucket names must be globally unique across all AWS accounts. Append your name or account ID:
- `frandorr-lambda-tests-789196964947`

### "The image manifest is not supported"
The Docker image was built with an unsupported manifest format. The `deploy.sh` script now uses:
```bash
DOCKER_BUILDKIT=1 docker buildx build --provenance=false
```

### "Requires capabilities: [CAPABILITY_NAMED_IAM]"
Fixed in `deploy.sh` by using `--capabilities CAPABILITY_NAMED_IAM` for CloudFormation.

### "Lambda was unable to configure your environment variables"
Don't set `AWS_DEFAULT_REGION` in the Lambda environment variables - it's reserved. The `infrastructure.yaml` template excludes it.

### "Not authorized to perform: logs:CreateLogGroup"
The IAM user needs CloudWatch Logs permissions, or you can remove the explicit log group from `infrastructure.yaml` (Lambda creates it automatically).

### Disk Space Issues During Build

The build context is large (~4GB with all plugins). If you run out of disk space:

```bash
# Clean Docker build cache
docker builder prune -af

# Clean Docker system
docker system prune -af --volumes

# Check disk usage
df -h
```

### Stack in DELETE_FAILED State

If a previous deployment failed and left the stack in a bad state:

```bash
# Force delete, retaining resources that can't be deleted
aws cloudformation delete-stack --stack-name ikd --retain-resources AereoLambdaLogGroup

# Wait for deletion, then retry deployment
sleep 30
./deploy.sh ikd us-west-2 ikd frandorr-lambda-tests
```

### "[Errno 30] Read-only file system: '/var/task/s3:'"

**Cause:** The pipeline `Writer` is trying to write to a path derived from `task.output_uri`, which is an S3 URI (e.g., `s3://bucket/path`). When treated as a local path, it becomes `/var/task/s3:/...` which is read-only in Lambda.

**Fix:** Ensure the job's `output_uri` is a local path inside `/tmp` (e.g., `/tmp/aereo_extraction`) so the writer has a writable destination. The Lambda handler then uploads the resulting files to S3.

### "ImportError: libexpat.so.1: cannot open shared object file"

**Cause:** GDAL (used by rasterio) requires the `expat` XML parsing library, which is not in the Lambda Python base image.

**Fix:** Add `RUN dnf install -y expat` to the Dockerfile. See "Fixes Applied → System Libraries" above.

### "Generic S3 error: Received redirect without LOCATION"

**Cause:** Accessing a public S3 bucket (like `noaa-goes19`) from a Lambda in a different AWS region. The bucket is in `us-east-1` but your Lambda is in another region.

**Fix:** The code now auto-detects `noaa-goes*` buckets and sets the correct region. See "Fixes Applied → Cross-Region S3 Access" above.

### "Lambda returned error" with no artifacts

**Cause:** The Lambda handler may not be uploading the actual GeoTIFF files, only metadata.

**Fix:** Ensure the Lambda handler iterates over artifacts and uploads each GeoTIFF file to S3. See "Fixes Applied → GeoTIFF Upload" above.

### CloudFormation Stack Shows "No changes to deploy"

**Cause:** The CloudFormation template hasn't changed, only the Docker image has.

**Fix:** The `deploy.sh` script updates the Lambda function code separately. If it doesn't, manually update:

```bash
aws lambda update-function-code \
  --function-name aereo-extractor \
  --image-uri $(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-west-2.amazonaws.com/ikd:latest \
  --region us-west-2
```

## Critical Fixes Applied

This deployment required several fixes to work correctly in the Lambda environment. These are documented here so you understand what was changed and why.

### 1. System Libraries (libexpat)

**Problem:** The `extract_aws_goes` and `extract_satpy` plugins use GDAL (via rasterio), which requires `libexpat.so.1`. The Lambda runtime base image doesn't include this.

**Fix:** Added system package installation to `Dockerfile.local`:

```dockerfile
# Install system libraries required by extractors (e.g. GDAL → libexpat)
RUN dnf install -y expat && dnf clean all
```

### 2. Temporary Directory for Local File Operations

**Problem:** Pipeline `Writer` stages were using `task.output_uri` as a local filesystem path. If the job was configured with an S3 URI, this resolved to `/var/task/s3:/...` which is on a read-only filesystem in Lambda.

**Fix:** Configure jobs with a local `/tmp` output URI (e.g. `/tmp/aereo_extraction`). The writer writes GeoTIFFs there, and the Lambda handler uploads them to S3:

```python
ExtractionJob(
    ...,
    output_uri="/tmp/aereo_extraction",
)
```

### 3. Cross-Region S3 Access (NOAA GOES Buckets)

**Problem:** NOAA GOES public buckets (`noaa-goes19`, `noaa-goes16`, etc.) are in `us-east-1`. When the Lambda runs in a different region (e.g., `us-west-2`), S3 returns a redirect error without a `LOCATION` header.

**Fix:** Added region detection in the asset downloader for NOAA buckets:

```python
if bucket.startswith("noaa-goes") and "region" not in opts:
    opts["region"] = "us-east-1"
```

File affected:
- `aereo/components/aereo/asset_downloader/_obstore_utils.py`

### 4. GeoTIFF Upload to S3

**Problem:** The Lambda handler originally only uploaded metadata (`artifacts.parquet` + `manifest.json`) but not the actual GeoTIFF raster files.

**Fix:** `lambda_handler/core.py` now uploads each GeoTIFF file and updates the artifact URIs to point to S3:

```python
for idx, row in artifacts.iterrows():
    local_path = Path(str(row["uri"]))
    if local_path.exists():
        rel_key = f"{out_prefix}{local_path.name}"
        s3.upload_file(str(local_path), out_bucket, rel_key)
        artifacts.at[idx, "uri"] = f"s3://{out_bucket}/{rel_key}"
```

### 5. Lambda Architecture Match

**Problem:** The CloudFormation template originally set `Architectures: [x86_64]` but the Docker image was built for `arm64` (the build server architecture).

**Fix:** Updated `infrastructure.yaml` to use `arm64`:

```yaml
Architectures:
  - arm64
```

Or build for the correct architecture:
```bash
docker buildx build --platform linux/amd64 ...  # for x86_64 Lambda
```

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Event JSON    │     │  S3 Download     │     │  ExtractConfig  │
│  (task_uri)     │────▶│  (task_assets    │────▶│  Pipeline       │
│                 │     │   + task_meta)   │     │  (TaskRunner)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Response JSON  │◄────│  S3 Upload       │◄────│  GeoDataFrame   │
│  (manifest_uri) │     │  (GeoTIFFs +     │     │  [ArtifactSchema]│
│                 │     │   artifacts)     │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Files Reference

| File | Description |
|------|-------------|
| `Dockerfile.local` | Multi-stage build with local plugins for testing |
| `Dockerfile` | Production build (installs plugins from PyPI) |
| `infrastructure.yaml` | CloudFormation template (IAM + Lambda) |
| `deploy.sh` | Automated deployment script |
| `docker-compose.yml` | Local testing with LocalStack + Lambda RIE |
| `test_local_lambda.py` | Local integration test script |
| `events/extraction-task.json` | Sample Lambda event payload |
| `test_pipeline/` | Synthetic reader/reprojector/writer for integration testing |

### Modified Files for Lambda Compatibility

These files were modified to work in the Lambda environment. If you're using the upstream versions, you'll need to apply similar fixes:

| File | Change | Why |
|------|--------|-----|
| `aereo/components/aereo/asset_downloader/_obstore_utils.py` | Auto-detect `us-east-1` for `noaa-goes*` buckets | Cross-region S3 access |
| `aereo/bases/aereo/lambda_handler/core.py` | Upload GeoTIFF files + update URIs | Results were metadata-only |
| Job configuration | Use `/tmp/...` for `output_uri` | Read-only filesystem in Lambda |

## Updating the Deployment

To deploy a new version after code changes:

```bash
cd /root/repos/aereo/projects/aereo-lambda
./deploy.sh ikd us-west-2 ikd frandorr-lambda-tests
```

The script will:
1. Rebuild the Docker image with your latest code
2. Push the new image to ECR
3. Update the Lambda function with the new image

**Note:** If CloudFormation reports "No changes to deploy", the Lambda function code still gets updated because the Docker image digest changes.

## Next Steps

- Test locally with `test_local_lambda.py` first (using LocalStack)
- Monitor logs in AWS CloudWatch: `/aws/lambda/aereo-extractor`
- Consider adding VPC configuration for private subnet access
- Set up CI/CD pipeline (GitHub Actions, GitLab CI, etc.) for automated deployments
- For production: use `Dockerfile` (installs from PyPI) instead of `Dockerfile.local`
