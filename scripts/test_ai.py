#!/usr/bin/env python3
"""
Test remplacement de fond IA.
Exécuter : python scripts/test_ai.py [chemin_photo]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import os; os.chdir(Path(__file__).parent.parent)

from config import load_config, Config

# Activer l'IA pour ce test même si désactivée dans config
raw = load_config()
raw.setdefault("ai", {})["enabled"] = True
raw["ai"].setdefault("provider", "rembg")
config = Config(raw)

from processing.ai_background import AIBackgroundProcessor

print("PhotoBooth — Test IA remplacement de fond\n")
print(f"Provider : {config.get('ai.provider')}")

ai = AIBackgroundProcessor(config)

if not ai.should_apply:
    print("ERREUR : IA non disponible après initialisation.")
    print("Installez rembg : pip install rembg onnxruntime")
    sys.exit(1)

# Photo de test
input_photo = sys.argv[1] if len(sys.argv) > 1 else "photos/test_capture.jpg"
if not Path(input_photo).exists():
    print(f"Photo de test introuvable : {input_photo}")
    print("Exécutez d'abord scripts/test_camera.py")
    sys.exit(1)

out = "photos/test_ai_result.jpg"
Path("photos").mkdir(exist_ok=True)

print(f"Traitement de : {input_photo}")
t0 = time.time()
result = ai.process(input_photo, out)
elapsed = time.time() - t0

if result == out and Path(out).exists():
    size = Path(out).stat().st_size
    print(f"Résultat : {out} ({size // 1024} Ko)")
    print(f"Durée    : {elapsed:.1f}s")
    print("Test OK ✓")
else:
    print(f"AVERTISSEMENT : résultat = {result} (fallback vers photo originale)")
    print(f"Durée : {elapsed:.1f}s")
