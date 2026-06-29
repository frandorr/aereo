# Run Aereo

AEREO gives you two interfaces for the same pipeline:

- **Python API** — best for notebooks and scripts.
- **CLI** — best for cron jobs, CI/CD, and headless servers.

Both use the same [Hydra](https://hydra.cc/) config packages, so you can start
in a notebook and move the exact same config to the CLI without rewriting
anything.

<div class="grid cards" markdown>

-   ## Python API

    ---

    `ExtractionJob.load_from_config()` → `job.search()` →
    `job.build_tasks()` → `job.execute()`.

    [:octicons-arrow-right-24: Run with Python](run-with-python.md)

-   ## CLI

    ---

    `aereo action=run search=... grid_dist=... patch_config=... read=... write=...`

    [:octicons-arrow-right-24: Run with CLI](run-with-cli.md)

-   ## AWS Lambda

    ---

    Deploy the Lambda handler and dispatch serialized tasks from your machine.

    [:octicons-arrow-right-24: Run on Lambda](run-on-lambda.md)

</div>
