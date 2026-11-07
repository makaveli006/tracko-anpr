"""Vehicle ANPR proof of concept: detection, tracking and number plate recognition."""

import os

# Ultralytics installs missing packages by itself, behind uv's back, and the next `uv sync`
# removes them again. Turn that off so a missing package fails loudly and gets added with `uv add`.
# This must be set before `ultralytics` is imported anywhere, which is why it lives here.
os.environ.setdefault("YOLO_AUTOINSTALL", "False")


def main() -> None:
    """Entry point for the `tracko-anpr` command."""
    from tracko_anpr.cli import main as cli_main

    raise SystemExit(cli_main())
