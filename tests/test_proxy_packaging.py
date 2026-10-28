"""Verify firmware source preparation cannot mutate or silently replace SDK input."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def package(tmp_path, monkeypatch):
    tools = Path(__file__).parents[1] / "tools/proxy_security"
    monkeypatch.syspath_prepend(str(tools))
    installer = importlib.import_module("prepare_sdk_patch")
    source = (tools / "smp_check_auth_req.c").read_bytes()
    monkeypatch.setattr(installer, "EXPECTED_SOURCE_SHA256", hashlib.sha256(source).hexdigest())
    sdk = tmp_path / "shared-sdk"
    original = sdk / installer.SDK_RELATIVE_SOURCE
    original.parent.mkdir(parents=True)
    original.write_bytes(source)
    (sdk / "unrelated-component.txt").write_text("not part of the deployed bt component")
    return installer, sdk, tmp_path / "production-bt", original


def test_component_preparation_is_scoped_idempotent_and_does_not_share_writable_files(package):
    installer, sdk, output, original = package
    before = original.read_bytes()
    component = installer.prepare(sdk, output)
    assert component == output / "components/bt"
    assert not (output / "unrelated-component.txt").exists()
    patched = output / installer.SDK_RELATIVE_SOURCE
    assert patched.read_text() == installer.fix_source(before.decode())
    assert original.read_bytes() == before
    assert installer.prepare(sdk, output) == component
    metadata = json.loads((output / "panasonic-bond-fix.json").read_text())
    assert metadata["patched_source_sha256"] == hashlib.sha256(patched.read_bytes()).hexdigest()
    patched.write_text("test output mutation")
    assert original.read_bytes() == before


def test_unknown_sdk_is_rejected_before_output_is_created(package):
    installer, sdk, output, original = package
    original.write_text(original.read_text() + "\n/* unknown revision */\n")
    with pytest.raises(ValueError, match="fingerprint"):
        installer.prepare(sdk, output)
    assert not output.exists()


def test_existing_modified_component_is_never_overwritten(package):
    installer, sdk, output, original = package
    installer.prepare(sdk, output)
    modified = output / installer.SDK_RELATIVE_SOURCE
    modified.write_text("user modification")
    with pytest.raises(ValueError, match="refusing to replace"):
        installer.prepare(sdk, output)
    assert modified.read_text() == "user modification"


def test_failed_copy_leaves_no_partial_production_component(package, monkeypatch):
    installer, sdk, output, original = package
    before = original.read_bytes()

    def fail_copy(source, destination, **kwargs):
        destination.mkdir(parents=True)
        raise OSError("simulated out of space")

    monkeypatch.setattr(installer.shutil, "copytree", fail_copy)
    with pytest.raises(OSError, match="out of space"):
        installer.prepare(sdk, output)
    assert not output.exists()
    assert original.read_bytes() == before
    assert not list(output.parent.glob(f".{output.name}-*"))


def test_output_inside_shared_sdk_is_rejected(package):
    installer, sdk, output, original = package
    with pytest.raises(ValueError, match="outside the shared SDK"):
        installer.prepare(sdk, sdk / "accidental-output")
