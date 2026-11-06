"""The number plate reader: Awiros-ANPR-OCR, in its own environment and process."""


def main() -> None:
    """Entry point for the `anpr-ocr` command."""
    from anpr_ocr.cli import main as cli_main

    raise SystemExit(cli_main())
