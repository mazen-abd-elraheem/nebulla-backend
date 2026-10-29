import os
import sys
import time

# Direct all Hugging Face caches and temp files to drive D:
os.environ["HF_HOME"] = r"D:\huggingface_cache"
os.environ["HF_HUB_CACHE"] = r"D:\huggingface_cache\hub"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from huggingface_hub import snapshot_download

TARGET_DIR = r"D:\models\voicetut-tts"
REPO_ID = "mohammedaly22/VoiceTut-TTS"

def download():
    print(f"=== Starting VoiceTut-TTS Download ===")
    print(f"Source Repo: {REPO_ID}")
    print(f"Destination: {TARGET_DIR}")
    print(f"HuggingFace Cache: {os.environ['HF_HOME']}")
    start = time.time()
    
    os.makedirs(TARGET_DIR, exist_ok=True)
    
    snapshot_path = snapshot_download(
        repo_id=REPO_ID,
        local_dir=TARGET_DIR,
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    
    elapsed = time.time() - start
    print(f"\n=== Download Complete in {elapsed:.1f} seconds ===")
    
    # Verify downloaded files
    expected_file = os.path.join(TARGET_DIR, "model.safetensors")
    if os.path.exists(expected_file):
        size_gb = os.path.getsize(expected_file) / (1024**3)
        print(f"Verified model.safetensors: {size_gb:.2f} GB")
    else:
        print("WARNING: model.safetensors not found!")

    # Check reference speakers
    refs = os.path.join(TARGET_DIR, "reference_speakers", "references.json")
    if os.path.exists(refs):
        print(f"Verified references.json exists")
    else:
        print("WARNING: references.json not found!")

    print("VoiceTut-TTS download & verification finished successfully!")

if __name__ == "__main__":
    download()
