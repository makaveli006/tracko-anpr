"""List what a PyTorch `.pt` file would import if it were loaded, without loading it.

A `.pt` checkpoint is a zip archive holding a Python pickle. Loading a pickle can run
code, because a pickle names functions for Python to import and call. This script only
reads the pickle's instructions (`pickletools`), so nothing in the file is executed.

A normal Ultralytics checkpoint imports from `torch`, `ultralytics`, `collections`,
`numpy` and a few standard-library helpers. Anything else is reported.

Standard library only, so it runs with any Python:
    python tools/plate_detector_eval/scan_weights.py pretrained-numberplate-weight
"""

from __future__ import annotations

import pickletools
import sys
import zipfile
from pathlib import Path

# Top-level packages a genuine Ultralytics checkpoint refers to.
EXPECTED_PACKAGES = {"torch", "ultralytics", "collections", "numpy", "_codecs", "copyreg", "pathlib", "datetime"}
# From `builtins`, only plain data types are expected.
EXPECTED_BUILTINS = {
    "set", "frozenset", "dict", "list", "tuple", "slice", "range", "int", "float", "bool", "complex",
    "bytes", "bytearray", "str", "object", "getattr",
}  # fmt: skip
# Never acceptable in a model file: these reach the operating system, the network or the interpreter.
DANGEROUS_PACKAGES = {
    "os", "posix", "nt", "subprocess", "sys", "shutil", "socket", "importlib", "runpy", "pty", "ctypes",
    "pickle", "marshal", "code", "codeop", "webbrowser", "multiprocessing", "threading", "asyncio",
    "urllib", "http", "requests", "ftplib", "smtplib", "base64", "zlib", "tempfile", "glob", "pip",
    "platform", "signal", "builtins.eval", "builtins.exec", "builtins.compile", "builtins.open",
    "builtins.__import__", "builtins.breakpoint", "builtins.input",
}  # fmt: skip

STRING_OPCODES = {"SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8", "UNICODE", "SHORT_BINSTRING", "BINSTRING", "STRING"}


def pickle_members(path: Path) -> list[tuple[str, bytes]]:
    """Every pickle inside the file: the `data.pkl` of a zip checkpoint, or the file itself if it is a bare pickle."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            return [(name, archive.read(name)) for name in archive.namelist() if name.endswith(".pkl")]
    return [(path.name, path.read_bytes())]


def referenced_globals(data: bytes) -> set[tuple[str, str]]:
    """Every (module, name) pair the pickle asks Python to import."""
    found: set[tuple[str, str]] = set()
    memo: dict[int, object] = {}
    recent: list[object] = []  # values pushed lately; only strings matter here

    for opcode, argument, _ in pickletools.genops(data):
        name = opcode.name
        if name in STRING_OPCODES:
            recent.append(argument)
        elif name == "GLOBAL":
            module, _, attribute = str(argument).partition(" ")
            found.add((module, attribute))
            recent.append(None)
        elif name == "STACK_GLOBAL":
            strings = [value for value in recent[-2:]]
            if len(strings) == 2 and all(isinstance(value, str) for value in strings):
                found.add((strings[0], strings[1]))
            else:
                found.add(("<could not resolve>", "<could not resolve>"))
            recent.append(None)
        elif name == "MEMOIZE":
            memo[len(memo)] = recent[-1] if recent else None
        elif name in {"BINPUT", "LONG_BINPUT", "PUT"}:
            memo[int(argument)] = recent[-1] if recent else None
        elif name in {"BINGET", "LONG_BINGET", "GET"}:
            recent.append(memo.get(int(argument)))
        else:
            recent.append(None)
        del recent[:-4]
    return found


def classify(found: set[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """Split the imports into dangerous ones and merely unexpected ones."""
    dangerous, unexpected = [], []
    for module, attribute in sorted(found):
        package = module.split(".")[0]
        full = f"{module}.{attribute}"
        if (
            package in DANGEROUS_PACKAGES
            or f"builtins.{attribute}" in DANGEROUS_PACKAGES
            and package
            in {
                "builtins",
                "__builtin__",
            }
        ):
            dangerous.append(full)
        elif package in {"builtins", "__builtin__"}:
            if attribute not in EXPECTED_BUILTINS:
                unexpected.append(full)
        elif package not in EXPECTED_PACKAGES:
            unexpected.append(full)
    return dangerous, unexpected


def scan(path: Path) -> dict:
    found: set[tuple[str, str]] = set()
    for _, data in pickle_members(path):
        found |= referenced_globals(data)
    dangerous, unexpected = classify(found)
    packages = sorted({module.split(".")[0] for module, _ in found})
    verdict = "DANGEROUS" if dangerous else "unexpected imports" if unexpected else "clean"
    return {
        "file": path,
        "imports": len(found),
        "packages": packages,
        "dangerous": dangerous,
        "unexpected": unexpected,
        "verdict": verdict,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    target = Path(argv[1])
    files = sorted(target.rglob("*.pt")) if target.is_dir() else [target]
    if not files:
        print(f"No .pt files under {target}")
        return 1

    worst = 0
    for path in files:
        result = scan(path)
        shown = path.relative_to(target) if target.is_dir() else path.name
        print(f"{result['verdict']:<19} {shown}")
        print(f"    {result['imports']} imports from: {', '.join(result['packages'])}")
        for label in ("dangerous", "unexpected"):
            if result[label]:
                print(f"    {label}: {', '.join(result[label][:12])}{' ...' if len(result[label]) > 12 else ''}")
        worst = max(worst, 2 if result["dangerous"] else 1 if result["unexpected"] else 0)
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
