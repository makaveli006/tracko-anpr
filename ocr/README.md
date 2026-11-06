# anpr-ocr

The number plate reader. It runs in its own environment (`ocr/.venv`) and as its own process, separate from the main application, because PaddlePaddle and PyTorch need different versions of the same NVIDIA library (cuDNN). See "CUDA and GPU Library Compatibility" in [../ARCHITECTURE.md](../ARCHITECTURE.md).

Run every command for this project from inside `ocr/`. It is not a uv workspace member and has its own `uv.lock`.

## What it depends on outside its own packages

Neither of these is in git, so this file is the record of exactly which versions the project uses.

### PaddleOCR source code

The Awiros model is not a pip-installable pipeline. Its network is built from PaddleOCR's `ppocr` source, which must be present at `ocr/vendor/PaddleOCR` (git-ignored).

| | |
|---|---|
| Repository | https://github.com/PaddlePaddle/PaddleOCR |
| Version | tag `v3.7.0` |
| Commit | `b03f46425e8ff4442b268ce449e3eef758146cd4` |

Get it (run from the repository root, in WSL):

```bash
git clone --depth 1 --branch v3.7.0 https://github.com/PaddlePaddle/PaddleOCR.git ocr/vendor/PaddleOCR
```

### Awiros-ANPR-OCR model

Stored in `models/awiros/` at the repository root (git-ignored).

| | |
|---|---|
| Source | https://huggingface.co/Awiros/anpr-ocr |
| Revision | `eadbc5ae4faa8284c8a547a60142fd555c3059ca` |
| Licence | Apache-2.0 |
| `model.safetensors` SHA-256 | `f9f1264e0c115a239ca6d6700a74ceffab17168b75dafc6c169c232012c68e47` |
| `en_dict.txt` SHA-256 | `0a94bb85eb456a04aae7ba2505fde280818649440e122922adcc5f3ab073dc72` |

`models/awiros/test.py` is Awiros's own inference script. It is the reference for how the network is configured and how the weights are loaded; it is not run as part of the application.

Get the files (run from the repository root):

```bash
mkdir -p models/awiros
for f in model.safetensors en_dict.txt LICENSE README.md requirements.txt test.py; do curl -L -o models/awiros/$f https://huggingface.co/Awiros/anpr-ocr/resolve/main/$f; done
```

## Model input and output

- **Input:** a cropped number plate image, resized to 48 pixels high and at most 320 wide.
- **Output:** the plate text in upper case, and a CTC confidence between 0 and 1.
- **Characters:** 0-9, A-Z, a-z and space.
