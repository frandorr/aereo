# AEREO Remote Extract — Custom Reader Example

This example shows how to package a custom :class:`aereo.interfaces.Reader` on
top of the published `ghcr.io/frandorr/aereo-extract-base` image and run it
locally via HTTP.

## Files

- `my_reader/__init__.py` — custom `SyntheticReader` plugin.
- `Dockerfile` — user image based on `aereo-extract-base`.
- `docker-compose.yml` — runs the HTTP server on port 8080.
- `invoke_local.py` — sends a direct extraction task to the local container.

## Local usage

1. Build and start the container:

   ```bash
   docker compose up --build -d
   ```

2. Send a task:

   ```bash
   pip install requests
   python invoke_local.py
   ```

3. Inspect results:

   ```bash
   ls ./output
   ```

## AWS Lambda deployment

Push the image to ECR and create/update a Lambda function whose handler is:

```text
aereo_extract.handlers.handle_lambda
```

The same image works both locally (HTTP server) and in Lambda (handler function).
