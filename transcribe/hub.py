"""Hugging Face downloads pinned to a commit.

onnx-asr and parakeet-mlx both fetch the newest commit of a model repository,
so a change upstream would reach the app unnoticed. Every model either engine
offers by default is pinned here; moving a pin is a deliberate edit.
"""

from __future__ import annotations

import os

REVISIONS = {
    "istupakov/parakeet-tdt-0.6b-v2-onnx": "0bbb45a3365852604aef28b538a8f066f4ccaa85",
    "istupakov/parakeet-tdt-0.6b-v3-onnx": "8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce",
    "mlx-community/parakeet-tdt-0.6b-v2": "8ae155301e23d820d82aa60d24817c900e69e487",
}


def hub_cache():
    home = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
    return os.environ.get("HF_HUB_CACHE") or os.path.join(home, "hub")


def snapshot_dir(repo):
    """Where the pinned (or, unpinned, any) snapshot of `repo` would be cached."""
    snapshots = os.path.join(hub_cache(), "models--" + repo.replace("/", "--"), "snapshots")
    revision = REVISIONS.get(repo)
    return os.path.join(snapshots, revision) if revision else snapshots


def pinned_snapshot(repo, allow_patterns=None):
    """A local directory holding `repo` at its pinned commit, downloading it
    the first time. None for a repository that isn't pinned, so the engine
    falls back to its own download."""
    revision = REVISIONS.get(repo)
    if revision is None:
        return None
    from huggingface_hub import snapshot_download

    try:
        # A cached launch never contacts the Hub.
        return snapshot_download(repo, revision=revision, allow_patterns=allow_patterns,
                                 local_files_only=True)
    except Exception:
        return snapshot_download(repo, revision=revision, allow_patterns=allow_patterns)
