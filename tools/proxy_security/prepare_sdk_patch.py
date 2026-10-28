"""Prepare an isolated IDF tree; never mutate ESPHome's shared framework cache."""

import difflib
import hashlib
import os
import shutil
from pathlib import Path

from sdk_bond_fix import SDK_RELATIVE_SOURCE, fix_source

original = Path("/root/.cache/esphome/idf/frameworks/5.5.6")
patched = Path("/data/panasonic-idf-5.5.6-bond-reuse")
relative = SDK_RELATIVE_SOURCE
source = (original / relative).read_text()
fixed = fix_source(source)
before = hashlib.sha256((original / relative).read_bytes()).hexdigest()
if not patched.exists():

    def copy(src, dst):
        try:
            return os.link(src, dst)
        except OSError:
            return shutil.copy2(src, dst)

    shutil.copytree(original, patched, copy_function=copy, symlinks=True)
    target = patched / relative
    temp = target.with_suffix(".panasonic-tmp")
    temp.write_text(fixed)
    temp.replace(target)
else:
    assert (patched / relative).read_text() == fixed, "Isolated SDK differs from expected patch"
assert hashlib.sha256((original / relative).read_bytes()).hexdigest() == before
print("Original SDK unchanged:", before)
print("Isolated SDK:", patched)
print(
    "".join(
        difflib.unified_diff(
            source.splitlines(True),
            fixed.splitlines(True),
            fromfile="a/" + str(relative),
            tofile="b/" + str(relative),
        )
    )
)
