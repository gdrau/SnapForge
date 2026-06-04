#!/usr/bin/env python3
"""
Test caméra Picamera2.
Exécuter sur le Raspberry Pi : python scripts/test_camera.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import os; os.chdir(Path(__file__).parent.parent)

from config import load_config, Config
from camera.picamera2_camera import create_camera

config = Config(load_config())
camera = create_camera(config)

print("PhotoBooth — Test Caméra\n")

# Test preview
print("1. Démarrage preview 5s…")
frames = {"count": 0}

def on_frame(frame):
    frames["count"] += 1

camera.start_preview(on_frame)
time.sleep(5)
camera.stop_preview()
print(f"   Frames reçues : {frames['count']} ({frames['count']/5:.1f} fps)")

# Test capture
print("\n2. Capture photo…")
out = "photos/test_capture.jpg"
Path("photos").mkdir(exist_ok=True)
try:
    path = camera.capture(out)
    size = Path(path).stat().st_size
    print(f"   Sauvegardé : {path} ({size // 1024} Ko)")

    from PIL import Image
    img = Image.open(path)
    print(f"   Dimensions : {img.width}×{img.height} px")
    print("   Capture OK ✓")
except Exception as e:
    print(f"   ERREUR : {e}")

camera.close()
print("\nTest terminé.")
