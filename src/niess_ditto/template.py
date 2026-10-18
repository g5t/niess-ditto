"""The file-writer's template: the structure's static datasets, written once.

A start message that names its instrument, as NICOS' does, makes kafka-to-nexus copy
``<template prefix>/<instrument>/<instrument>.hdf`` and add the message's structure to
the copy: groups that exist are reused, datasets that exist are kept as they are, and
stream writers and links come only from the message. So, as at ESS, the template holds
every dataset of the structure, made by kafka-to-nexus' own ``template-maker``, and the
start message only what is written during the run.

A dataset in the template cannot be changed by a start message, so what NICOS adds per
run (title, users, sample) must not be in the structure the template is made from.
"""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def _is_dataset(node):
    return node.get("module") == "dataset" or node.get("type") == "dataset"


def without_datasets(structure: dict) -> dict:
    """A copy of ``structure`` without its dataset modules: groups, streams and links."""
    out = {k: v for k, v in structure.items() if k != "children"}
    if "children" in structure:
        out["children"] = [without_datasets(c) for c in structure["children"]
                           if not (isinstance(c, dict) and _is_dataset(c))]
    return out


def version(structure: dict) -> str:
    """Identifies the structure a template was made from."""
    text = json.dumps(structure, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def make_template(structure_json, work, instrument, maker="template-maker") -> Path:
    """Write the template the writer in ``work`` copies, unless it is up to date."""
    import h5py

    structure = json.loads(Path(structure_json).read_text())
    wanted = version(structure)
    path = Path(work) / instrument / f"{instrument}.hdf"
    if path.exists():
        with h5py.File(path, "r") as file:
            if file.attrs.get("template_version") == wanted:
                return path
    if shutil.which(maker) is None:
        raise FileNotFoundError(f"{maker}, kafka-to-nexus' template maker, is not on PATH")
    path.parent.mkdir(parents=True, exist_ok=True)
    source = path.with_suffix(".json")
    source.write_text(json.dumps({**structure, "template_version": wanted}))
    made = path.with_suffix(".new.hdf")
    made.unlink(missing_ok=True)
    subprocess.run([maker, "-f", str(source), "-i", instrument, "-o", str(made)],
                   check=True, capture_output=True, text=True)
    # template-maker leaves its file read-only, and the writer's copy keeps the mode
    made.chmod(0o644)
    os.replace(made, path)
    return path
