# ---------------------------------------------------------------------------
# Stage 1 — Builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build toolchain
RUN pip install --no-cache-dir hatch hatch-polylith-bricks

# Copy workspace layout (only what Hatch needs to resolve bricks)
COPY pyproject.toml workspace.toml ./
COPY components/ components/
COPY bases/ bases/
COPY projects/aer-lambda/ projects/aer-lambda/

# Build the wheel
RUN cd projects/aer-lambda && hatch build -t wheel

# ---------------------------------------------------------------------------
# Stage 2 — Lambda Runtime
# ---------------------------------------------------------------------------
FROM public.ecr.aws/lambda/python:3.12

# Install the wheel + runtime deps
COPY --from=builder /build/projects/aer-lambda/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl

# AWS Lambda handler entrypoint
CMD ["aer.lambda_handler.core.handler"]
