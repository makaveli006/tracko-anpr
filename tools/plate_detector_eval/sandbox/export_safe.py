"""Re-save a chosen candidate in a form that cannot carry code. Runs INSIDE the sandbox container only.

A `.pt` file is a Python pickle and can run code when loaded. This script loads it here, where
that is contained, and writes out only plain data:

    <name>.safetensors   the network's numbers (safetensors holds tensors and nothing else)
    <name>.yaml          the network's layout, as text, exactly as stored in the checkpoint
    <name>.json          where it came from: source file, checksum, class names, training settings

The application then rebuilds the network from the layout with its own installed Ultralytics
code and loads the numbers into it, never touching the original file.

Usage (inside the container):  python /work/export_safe.py <file under /weights> <name>
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file
from ultralytics import YOLO
from ultralytics.nn.tasks import DetectionModel
from ultralytics.utils import YAML

WEIGHTS, OUT = Path("/weights"), Path("/out")


def main(relative: str, name: str) -> int:
    source = WEIGHTS / relative
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()

    yolo = YOLO(str(source), task="detect")
    network = yolo.model.float().eval()
    layout = dict(network.yaml)
    names = {int(key): str(value) for key, value in dict(network.names).items()}
    layout["nc"] = len(names)
    # The layout must carry its own size letter (n, s, m, ...). Ultralytics otherwise guesses it from
    # the file name, and a wrong guess silently builds a network of the wrong size.
    if not layout.get("scale"):
        raise SystemExit("The checkpoint's layout has no 'scale'; refusing to export a model of unknown size.")

    state = {key: value.detach().cpu().float().contiguous() for key, value in network.state_dict().items()}
    weights_file = OUT / f"{name}.safetensors"
    save_file(state, str(weights_file))
    YAML.save(OUT / f"{name}.yaml", layout)

    # The settings the author trained with, as recorded in the checkpoint itself.
    train_args = dict((yolo.ckpt or {}).get("train_args") or {})
    keep = ("model", "data", "epochs", "imgsz", "batch", "task")
    details = {
        "name": name,
        "source_file": relative,
        "source_sha256": checksum,
        "weights_file": weights_file.name,
        "weights_sha256": hashlib.sha256(weights_file.read_bytes()).hexdigest(),
        "class_names": names,
        "scale": layout["scale"],
        "stride": [int(value) for value in network.stride.tolist()],
        "tensors": len(state),
        "parameters": int(sum(value.numel() for value in network.parameters())),
        "trained_with": {key: str(train_args[key]) for key in keep if key in train_args},
        "exported_with_ultralytics": __import__("ultralytics").__version__,
    }
    (OUT / f"{name}.json").write_text(json.dumps(details, indent=2), encoding="utf-8")

    # Self-check, still inside the sandbox: rebuild from the plain files and compare with the original.
    # The layout is passed as a dictionary, not a path, so the size letter saved in it is the one used.
    saved_layout = YAML.load(OUT / f"{name}.yaml")
    rebuilt = DetectionModel(cfg=saved_layout, ch=3, nc=len(names), verbose=False).float().eval()
    rebuilt.load_state_dict(load_file(str(weights_file)), strict=True)
    torch.manual_seed(0)
    sample = torch.rand(2, 3, 640, 640)
    with torch.no_grad():
        original_out, rebuilt_out = network(sample), rebuilt(sample)

    def first_tensor(output):
        while not isinstance(output, torch.Tensor):
            output = output[0] if not isinstance(output, dict) else next(iter(output.values()))
        return output

    difference = float((first_tensor(original_out) - first_tensor(rebuilt_out)).abs().max())
    print(f"source      : {relative}")
    print(f"sha256      : {checksum}")
    print(f"classes     : {names}")
    print(f"tensors     : {len(state)}, parameters: {details['parameters']:,}")
    print(f"layout      : scale {layout.get('scale')}, nc {layout['nc']}, yaml file {layout.get('yaml_file')}")
    print(f"trained with: {details['trained_with']}")
    print(f"rebuilt-from-plain-files output differs from the original by at most {difference:.2e}")
    print(f"wrote       : {name}.safetensors ({weights_file.stat().st_size / 1e6:.1f} MB), {name}.yaml, {name}.json")
    return 0 if difference < 1e-4 else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
