#!/usr/bin/env python3
"""
Test génération QR code.
Exécuter : python scripts/test_qr.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import os; os.chdir(ROOT)

from config import load_config, Config
from qr.qr_generator import QRGenerator

config = Config(load_config())
gen = QRGenerator(config)

print("SnapForge — Test QR Code\n")

out_dir = ROOT / "Photo" / "tests"
out_dir.mkdir(parents=True, exist_ok=True)
out = str(out_dir / "test_qrcode.png")

img = gen.generate("snapforge_20260101_120000.jpg", out)

if img is not None:
    abs_path = Path(out).resolve()
    print(f"QR code généré : {abs_path}")
    print(f"Dimensions     : {img.size}")
    base_url = config.get("qr.base_url", "http://photobooth.local/photos")
    print(f"URL encodée    : {base_url}/snapforge_20260101_120000.jpg")
    print("Test OK ✓")
else:
    print("ERREUR : QR code non généré")
    print("Vérifiez que qrcode est installé : pip install qrcode[pil]")
