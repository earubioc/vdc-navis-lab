"""Entry point of the MCPB bundle: starts the MCP server over stdio.

`uv run` installs the project declared in pyproject.toml (the `vdc_navis_lab` package under src/) and then runs this file.
"""
from vdc_navis_lab.server import main

raise SystemExit(main(["--serve"]))
