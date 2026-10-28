"""Build an isolated, version-checked Bluetooth component; never alter shared IDF."""

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from sdk_bond_fix import EXPECTED_SOURCE_SHA256, SDK_RELATIVE_SOURCE, SDK_VERSION, fix_source


def prepare(sdk_root: Path, output: Path) -> Path:
    """Atomically prepare only bt, retaining the shared SDK as read-only input."""
    sdk_root, output = sdk_root.resolve(), output.resolve()
    if output.is_relative_to(sdk_root):
        raise ValueError("The output must be outside the shared SDK")
    original = sdk_root / SDK_RELATIVE_SOURCE
    source = original.read_bytes()
    if hashlib.sha256(source).hexdigest() != EXPECTED_SOURCE_SHA256:
        raise ValueError(
            "SDK source fingerprint differs from tested IDF 5.5.6; review before patching"
        )
    fixed = fix_source(source.decode()).encode()
    target = output / SDK_RELATIVE_SOURCE
    if output.exists():
        if target.is_symlink() or not target.is_file() or target.read_bytes() != fixed:
            raise ValueError(
                "Existing component differs from the expected patch; refusing to replace it"
            )
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temp:
            staged = Path(temp) / "component"
            shutil.copytree(sdk_root / "components/bt", staged / "components/bt", symlinks=True)
            (staged / SDK_RELATIVE_SOURCE).write_bytes(fixed)
            if original.read_bytes() != source:
                raise RuntimeError("Shared SDK changed during preparation")
            staged.rename(output)
    metadata = {
        "sdk_version": SDK_VERSION,
        "original_source_sha256": EXPECTED_SOURCE_SHA256,
        "patched_source_sha256": hashlib.sha256(fixed).hexdigest(),
    }
    license_file = sdk_root / "LICENSE"
    if license_file.is_file():
        license_target = output / "LICENSE-ESP-IDF.txt"
        license_target.write_bytes(license_file.read_bytes())
    manifest = output / "panasonic-bond-fix.json"
    temporary = manifest.with_suffix(".tmp")
    temporary.write_text(json.dumps(metadata, indent=2) + "\n")
    temporary.replace(manifest)
    return output / "components/bt"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sdk-root", type=Path, default=Path("/root/.cache/esphome/idf/frameworks/5.5.6")
    )
    parser.add_argument("--output", type=Path, default=Path("/data/panasonic-idf-5.5.6-bond-reuse"))
    args = parser.parse_args()
    print("Patched Bluetooth component:", prepare(args.sdk_root, args.output))
    print("Shared SDK was not modified. No firmware was uploaded.")


if __name__ == "__main__":
    main()
