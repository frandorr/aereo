# Example user image built on the published AEREO extract base image.
# Build the base image first (see projects/aereo-extract/Dockerfile.base) or
# replace the FROM line with the published image once it is available.
FROM ghcr.io/frandorr/aereo-extract-base:latest

# Install any published pipeline plugins you need.
RUN pip install --no-cache-dir \
    aereo-extract-odc-stac || true

# Copy the local custom reader package.
COPY ./my_reader /opt/aereo/my_reader
ENV PYTHONPATH=/opt/aereo

# Default to the HTTP server. Override to aereo_extract.handlers.handle_lambda
# when deploying this image to AWS Lambda.
CMD ["aereo-extract-server"]
