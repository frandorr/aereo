# ---------------------------------------------------------------------------
# AER Lambda Container Image
# ---------------------------------------------------------------------------
# Build context must be the parent of the aer repo (e.g. /root/repos) so
# sibling plugin repositories are visible:
#
#   cd /root/repos
#   docker build -f aer/projects/aer-lambda/Dockerfile -t aer-lambda:latest .
#
# For local testing with docker compose:
#   cd aer/projects/aer-lambda
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
# Copy AER workspace (what Hatch needs to resolve bricks)
# ------------------------------------------------------------------
COPY aer/pyproject.toml aer/workspace.toml ./
COPY aer/components/ components/
COPY aer/bases/ bases/
COPY aer/projects/aer-lambda/ projects/aer-lambda/
COPY aer/projects/aer-core/ projects/aer-core/

# ------------------------------------------------------------------
# Copy plugin repos (local editable dependencies)
# ------------------------------------------------------------------
COPY aereo-extract-remote/ aereo-extract-remote/
COPY aereo-extract-odc-stac/ aereo-extract-odc-stac/
COPY aereo-extract-satpy/ aereo-extract-satpy/

# ------------------------------------------------------------------
# Build wheels
# ------------------------------------------------------------------
RUN cd projects/aer-core && hatch build -t wheel
RUN cd projects/aer-lambda && hatch build -t wheel
RUN cd aereo-extract-remote && hatch build -t wheel
RUN cd aereo-extract-odc-stac/projects/aereo-extract-odc-stac && hatch build -t wheel
RUN cd aereo-extract-satpy/projects/aereo-extract-satpy && hatch build -t wheel

# ---------------------------------------------------------------------------
# Stage 2 — Lambda Runtime
# ---------------------------------------------------------------------------
FROM public.ecr.aws/lambda/python:3.12

# Install the AER Lambda wheel + all plugin wheels.
# pip resolves heavy geospatial runtime deps (rasterio, satpy, netcdf4, etc.)
# from binary wheels on PyPI.
COPY --from=builder /build/projects/aer-core/dist/*.whl /tmp/
COPY --from=builder /build/projects/aer-lambda/dist/*.whl /tmp/
COPY --from=builder /build/aereo-extract-remote/dist/*.whl /tmp/
COPY --from=builder /build/aereo-extract-odc-stac/dist/*.whl /tmp/
COPY --from=builder /build/aereo-extract-satpy/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl

# AWS Lambda handler entrypoint
CMD ["aer.lambda_handler.core.handler"]
