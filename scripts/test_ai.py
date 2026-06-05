#!/usr/bin/env python3
"""
Test remplacement de fond IA.
Exécuter : python scripts/test_ai.py [chemin_photo]
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import os; os.chdir(ROOT)

from config import load_config, Config

# Activer l'IA pour ce test même si désactivée dans config
raw = load_config()
raw.setdefault("ai", {})["enabled"] = True
raw["ai"].setdefault("provider", "rembg")
config = Config(raw)

from processing.ai_background import AIBackgroundProcessor

print("SnapForge — Test IA remplacement de fond\n")
print(f"Provider : {config.get('ai.provider')}")

ai = AIBackgroundProcessor(config)

if not ai.should_apply:
    print("ERREUR : IA non disponible après initialisation.")
    print("Installez rembg : pip install rembg onnxruntime")
    sys.exit(1)

# Photo de test
default_input = str(ROOT / "Photo" / "tests" / "test_capture.jpg")
input_photo = sys.argv[1] if len(sys.argv) > 1 else default_input

if not Path(input_photo).exists():
    print(f"Photo de test introuvable : {input_photo}")
    print("Exécutez d'abord : python scripts/test_camera.py")
    sys.exit(1)

out_dir = ROOT / "Photo" / "tests"
out_dir.mkdir(parents=True, exist_ok=True)
out = str(out_dir / "test_ai_result.jpg")

print(f"Traitement de  : {Path(input_photo).resolve()}")
t0 = time.time()
result = ai.process(input_photo, out)
elapsed = time.time() - t0

if result == out and Path(out).exists():
    abs_path = Path(out).resolve()
    size_ko = abs_path.stat().st_size // 1024
    print(f"Résultat       : {abs_path}")
    print(f"Taille         : {size_ko} Ko")
    print(f"Durée          : {elapsed:.1f}s")
    print("Test OK ✓")
else:
    print(f"AVERTISSEMENT  : fallback vers photo originale (résultat={result})")
    print(f"Durée          : {elapsed:.1f}s")
