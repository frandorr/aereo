# ---------------------------------------------------------------------------
# AEREO Lambda Container Image
# ---------------------------------------------------------------------------
# Build context must be the parent of the aereo repo (e.g. /root/repos):
#
#   cd /root/repos
#   docker build -f aereo/projects/aereo-lambda/Dockerfile -t aereo-lambda:latest .
#
# For local testing with docker compose:
#   cd aereo/projects/aereo-lambda
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
COPY aereo/pyproject.toml aereo/workspace.toml ./
COPY aereo/components/ components/
COPY aereo/bases/ bases/
COPY aereo/projects/aereo-lambda/ projects/aereo-lambda/
COPY aereo/projects/aereo/ projects/aereo/

# ------------------------------------------------------------------
# Build wheels
# ------------------------------------------------------------------
RUN cd projects/aereo && hatch build -t wheel
RUN cd projects/aereo-lambda && hatch build -t wheel
# ---------------------------------------------------------------------------
# Stage 2 — Lambda Runtime
# ---------------------------------------------------------------------------
FROM public.ecr.aws/lambda/python:3.12

# Install system libraries required by rasterio/GDAL at runtime.
RUN microdnf install -y expat \
    && microdnf clean all

# Install the AEREO Lambda wheel.
# pip resolves heavy geospatial runtime deps (rasterio, satpy, netcdf4, etc.)
# from binary wheels on PyPI.
COPY --from=builder /build/projects/aereo/dist/*.whl /tmp/
COPY --from=builder /build/projects/aereo-lambda/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl

# Install test pipeline plugin for local integration testing.
COPY --from=builder /build/projects/aereo-lambda/test_pipeline /tmp/test_pipeline
RUN pip install --no-cache-dir /tmp/test_pipeline && rm -rf /tmp/test_pipeline

# Install real pipeline plugins from PyPI (uncomment/modify as needed):
# RUN pip install aereo-extract-satpy

# AWS Lambda handler entrypoint
CMD ["aereo.lambda_handler.core.handler"]
