#!/usr/bin/env python3
"""
Diagnostic complet QR code — identifie exactement où ça échoue.
Exécuter : python scripts/test_qr.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import os; os.chdir(ROOT)

print("=" * 50)
print("DIAGNOSTIC QR CODE")
print("=" * 50)

errors = []

# 1. qrcode
print("\n[1] Import qrcode...")
try:
    import qrcode
    print(f"    OK  version = {getattr(qrcode, '__version__', '?')}")
except ImportError as e:
    print(f"    ECHEC : {e}")
    print("    → pip install qrcode[pil]")
    sys.exit(1)

# 2. Pillow
print("\n[2] Import Pillow...")
try:
    from PIL import Image
    print(f"    OK  version = {Image.__version__}")
except ImportError as e:
    print(f"    ECHEC : {e}")
    sys.exit(1)

# 3. Resampling filter
print("\n[3] Filtre de redimensionnement...")
try:
    resample = Image.Resampling.LANCZOS
    print("    OK  Image.Resampling.LANCZOS")
except AttributeError:
    try:
        resample = Image.LANCZOS  # type: ignore
        print("    OK  Image.LANCZOS (Pillow < 10)")
    except AttributeError as e:
        print(f"    ECHEC : {e}")
        sys.exit(1)

# 4. Génération QR
print("\n[4] Génération QR code...")
url = "http://snapforge.local/photos/test.jpg"
try:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    print(f"    OK  url = {url}")
except Exception as e:
    print(f"    ECHEC make : {e}")
    sys.exit(1)

# 5. make_image
print("\n[5] make_image...")
try:
    qr_img = qr.make_image(fill_color="black", back_color="white")
    print(f"    OK  type = {type(qr_img).__name__}")
    print(f"        attrs = {[a for a in dir(qr_img) if not a.startswith('_')][:8]}")
except Exception as e:
    print(f"    ECHEC : {e}")
    sys.exit(1)

# 6. Conversion RGB — plusieurs méthodes
print("\n[6] Conversion RGB...")
pil_img = None

# Méthode A : .convert()
try:
    pil_img = qr_img.convert("RGB")
    print(f"    OK  via .convert()  size={pil_img.size}  mode={pil_img.mode}")
except Exception as e:
    print(f"    Méthode A (.convert) échoue : {e}")

# Méthode B : .get_image() puis .convert()
if pil_img is None and hasattr(qr_img, 'get_image'):
    try:
        pil_img = qr_img.get_image().convert("RGB")
        print(f"    OK  via .get_image().convert()  size={pil_img.size}")
    except Exception as e:
        print(f"    Méthode B (.get_image) échoue : {e}")

# Méthode C : PIL direct
if pil_img is None:
    try:
        pil_img = Image.open(
            __import__("io").BytesIO(qr_img._img.tobytes())
        ).convert("RGB")
        print(f"    OK  via tobytes  size={pil_img.size}")
    except Exception as e:
        print(f"    Méthode C (tobytes) échoue : {e}")

if pil_img is None:
    print("    ECHEC : aucune méthode de conversion ne fonctionne")
    sys.exit(1)

# 7. Resize
print("\n[7] Resize 300×300...")
try:
    pil_resized = pil_img.resize((300, 300), resample)
    print(f"    OK  {pil_resized.size}")
except Exception as e:
    print(f"    ECHEC : {e}")
    sys.exit(1)

# 8. Sauvegarde PNG
print("\n[8] Sauvegarde fichier...")
out = ROOT / "Photo" / "tests" / "test_qr_direct.png"
out.parent.mkdir(parents=True, exist_ok=True)
try:
    pil_resized.save(str(out))
    print(f"    OK  {out}  ({out.stat().st_size} octets)")
except Exception as e:
    print(f"    ECHEC : {e}")
    sys.exit(1)

# 9. pygame.Surface
print("\n[9] Conversion pygame.Surface...")
try:
    import pygame
    pygame.init()
    surf = pygame.image.fromstring(pil_resized.tobytes(), pil_resized.size, "RGB")
    print(f"    OK  Surface {surf.get_size()}")
    pygame.quit()
except Exception as e:
    print(f"    ECHEC : {e}")
    errors.append(str(e))

print("\n" + "=" * 50)
if errors:
    print(f"RÉSULTAT : {len(errors)} problème(s)")
    for err in errors:
        print(f"  - {err}")
else:
    print("RÉSULTAT : Tous les tests réussis ✓")
    print(f"\nFichier QR sauvegardé : {out}")
    print("Vérifiez que le fichier s'ouvre correctement.")
