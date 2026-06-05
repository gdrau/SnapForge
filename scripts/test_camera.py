#!/usr/bin/env python3
"""
Test caméra Picamera2.
Exécuter sur le Raspberry Pi : python scripts/test_camera.py
"""
import sys
import time
from pathlib import Path

# Répertoire de travail = racine du projet
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import os; os.chdir(ROOT)

from config import load_config, Config
from camera.picamera2_camera import create_camera

config = Config(load_config())
camera = create_camera(config)

print("SnapForge — Test Caméra\n")

# Dossier de sortie
out_dir = ROOT / "Photo" / "tests"
out_dir.mkdir(parents=True, exist_ok=True)
out = str(out_dir / "test_capture.jpg")

# Test preview
print("1. Démarrage preview 5s...")
frames = {"count": 0}

def on_frame(frame):
    frames["count"] += 1

camera.start_preview(on_frame)
time.sleep(5)
camera.stop_preview()
fps = frames["count"] / 5
print(f"   Frames reçues : {frames['count']} ({fps:.1f} fps)")

if fps < 5:
    print("   AVERTISSEMENT : fps faibles, vérifiez la caméra")
else:
    print("   Preview OK ✓")

# Test capture
print("\n2. Capture photo...")
try:
    path = camera.capture(out)
    abs_path = Path(path).resolve()
    size_ko = abs_path.stat().st_size // 1024
    print(f"   Fichier    : {abs_path}")
    print(f"   Taille     : {size_ko} Ko")

    try:
        from PIL import Image
        img = Image.open(path)
        print(f"   Dimensions : {img.width} x {img.height} px")
    except ImportError:
        pass

    print("   Capture OK ✓")
except Exception as e:
    print(f"   ERREUR : {e}")

camera.close()
print(f"\nPhotos de test dans : {out_dir.resolve()}")
print("Test terminé.")
