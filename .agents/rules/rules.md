---
trigger: always_on
---

# Instructions that must be followed alway

1. **Always use `uv`**: Whenever running Python scripts, running project commands, or running tests, you MUST use `uv` as the package manager and test runner, rather than executing them with system `python` or naked `pytest`. For example, always run tests with `uv run pytest`.

2. **Never use `--no-verify` on commits**: Always run pre-commit hooks. If hooks fail, fix the issues rather than bypassing them.

3. **Polylith Architecture Test Paths**: This repository uses a Python Polylith architecture. The test path structure explicitly mimics the component paths.
   - For example, if a component is located at `components/aer/temporal/`, its tests must be placed in and run from `test/components/aer/temporal/`.
   - Always map the component path to the corresponding test path when debugging or executing tests for a specific component.

4. **When asked to commit something**: you MUST use git-commit skill

5. **Always use workflow poly-create to create components/bases/project for polylith**. Do NOT implement it in this step, just run the creation workflow.

6. If user ask for advise how to modify code, or an explanation use codebase-intro skill
