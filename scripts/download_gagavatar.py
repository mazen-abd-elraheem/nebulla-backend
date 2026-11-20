"""
Script to download xg-chu/GAGAvatar pre-trained model weights from HuggingFace.
Saves checkpoints to assets/GAGAvatar/ for local CUDA neural 3D Gaussian inference.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO_ID = "xg-chu/GAGAvatar"
TARGET_DIR = Path("assets/GAGAvatar")
TARGET_DIR.mkdir(parents=True, exist_ok=True)

FILES = [
    ("assets/FLAME_with_eye.pt", "FLAME_with_eye.pt"),
    ("assets/canonical.obj", "canonical.obj"),
    ("config.json", "config.json"),
    ("assets/GAGAvatar.pt", "GAGAvatar.pt"),
]


def download_all() -> None:
    print(f"🚀 Downloading GAGAvatar model assets from HuggingFace ('{REPO_ID}')...")
    print(f"Target directory: {TARGET_DIR.resolve()}\n")

    for remote_rel, local_name in FILES:
        dest_file = TARGET_DIR / local_name
        if dest_file.exists() and dest_file.stat().st_size > 1000:
            print(f"✓ {local_name} already exists ({dest_file.stat().st_size / (1024*1024):.2f} MB). Skipping.")
            continue

        print(f"📥 Downloading {remote_rel} ...")
        try:
            downloaded = hf_hub_download(
                repo_id=REPO_ID,
                filename=remote_rel,
            )
            shutil.copy2(downloaded, dest_file)
            size_mb = dest_file.stat().st_size / (1024 * 1024)
            print(f"✓ Successfully saved to {dest_file} ({size_mb:.2f} MB)")
        except Exception as exc:
            print(f"❌ Failed to download {remote_rel}: {exc}", file=sys.stderr)
            raise

    # Also clean up any extra nested assets directory if created
    nested_assets = TARGET_DIR / "assets"
    if nested_assets.is_dir():
        shutil.rmtree(nested_assets, ignore_errors=True)

    print("\n🎉 All GAGAvatar model assets downloaded successfully!")
    for f in TARGET_DIR.iterdir():
        if f.is_file():
            print(f" - {f.name}: {f.stat().st_size / (1024*1024):.2f} MB")


if __name__ == "__main__":
    download_all()
