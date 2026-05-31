# ---------------------------------------------------------------------------
# AEREO Lambda Container Image
# ---------------------------------------------------------------------------
# Build context must be the root of the aereo repo (e.g. /root/repos/aereo):
#
#   cd /root/repos/aereo
#   docker build -f projects/aereo-lambda/Dockerfile -t aereo-lambda:latest .
#
# For local testing with docker compose:
#   cd projects/aereo-lambda
#   docker compose up --build
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Stage 1 — Builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build toolchain
RUN pip install --no-cache-dir hatch hatch-polylith-bricks

# ------------------------------------------------------------------
# Copy AEREO workspace (what Hatch needs to resolve bricks)
# ------------------------------------------------------------------
COPY pyproject.toml workspace.toml ./
COPY components/ components/
COPY bases/ bases/
COPY projects/aereo-lambda/ projects/aereo-lambda/
COPY projects/aereo/ projects/aereo/

# ------------------------------------------------------------------
# Build wheels
# ------------------------------------------------------------------
RUN cd projects/aereo && hatch build -t wheel
RUN cd projects/aereo-lambda && hatch build -t wheel
# ---------------------------------------------------------------------------
# Stage 2 — Lambda Runtime
# ---------------------------------------------------------------------------
FROM public.ecr.aws/lambda/python:3.12

# Install the AEREO Lambda wheel.
# pip resolves heavy geospatial runtime deps (rasterio, satpy, netcdf4, etc.)
# from binary wheels on PyPI.
COPY --from=builder /build/projects/aereo/dist/*.whl /tmp/
COPY --from=builder /build/projects/aereo-lambda/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl

# Install test extractor plugin for local testing
COPY --from=builder /build/projects/aereo-lambda/test_extractor /tmp/test_extractor
RUN pip install --no-cache-dir /tmp/test_extractor && rm -rf /tmp/test_extractor

# Install real extractor plugins from PyPI (uncomment/modify as needed):
RUN pip install aereo-extract-satpy

# AWS Lambda handler entrypoint
CMD ["aereo.lambda_handler.core.handler"]
