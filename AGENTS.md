# Project Information

You are working on the code base of frugalbot, a Python-based coding agent harness. The source code is under src/ and the test code is under tests/. The folder layout under tests/ must match the one under src/ to easily find the test modules for a given source module.

## Project Guidelines
- You must use `uv` to manage dependencies and run the pytest tests.
- Ensure all code, including test code, has full type annotations (including return types) to strictly adhere to python strict typing requirements.
- Always minimize the length of the output of tools (eg. prefer to run multiple listfiles over running one that recurses over the whole tree).
- Consult `pyproject.toml` for project dependencies and settings.
- Write tests for any and all code you produce or modify.
- When writing test code, you must follow the guidelines in `docs/testing_guidelines.md`.
- When finished with a task, you must run the following in order, fix errors (never fix errors by adding a comment to ignore the error) and re-run until all errors have been resolved:
  - `uv run ruff format`
  - `uv run ruff check --fix`
  - `uv run pyright`
  - `uv run pytest -q`
