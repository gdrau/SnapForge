#!/usr/bin/env python3
"""
Test génération QR code.
Exécuter : python scripts/test_qr.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import os; os.chdir(Path(__file__).parent.parent)

from config import load_config, Config
from qr.qr_generator import QRGenerator

config = Config(load_config())
gen = QRGenerator(config)

print("PhotoBooth — Test QR Code\n")

out = "photos/test_qrcode.png"
Path("photos").mkdir(exist_ok=True)

img = gen.generate("photobooth_20260101_120000.jpg", out)

if img is not None:
    print(f"QR code généré : {out}")
    print(f"Dimensions : {img.size}")
    base_url = config.get("qr.base_url", "http://photobooth.local/photos")
    print(f"URL encodée : {base_url}/photobooth_20260101_120000.jpg")
    print("Test OK ✓")
else:
    print("ERREUR : QR code non généré")
    print("Vérifiez que qrcode est installé : pip install qrcode[pil]")
