# aereoeo-lambda

AER Lambda container image — a Polylith project that packages the AWS Lambda handler and a minimal subset of AER core bricks for serverless extraction tasks.

## Build

```bash
cd /root/repos/aereo
uv build --wheel projects/aereo-lambda
```

## Local testing

See `docker-compose.yml` (coming in a later phase) for RIE-based local invocation.
