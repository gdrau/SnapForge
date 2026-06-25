#!/usr/bin/env python3
"""
Test qualité photo à résolution maximale.
Exécuter sur le Raspberry Pi : python scripts/test_quality_photo.py

Capture plusieurs photos à la résolution native maximale du capteur
et mesure : dimensions, taille fichier, netteté, temps de capture.
"""
import sys
import time
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Résolutions connues par modèle (fallback si l'API ne répond pas)
# ---------------------------------------------------------------------------
KNOWN_MAX = {
    "imx477": (4056, 3040),   # HQ Camera
    "imx708": (4608, 2592),   # Module 3
    "imx219": (3280, 2464),   # Module 2
    "ov5647": (2592, 1944),   # Module 1
}

SEP = "─" * 60


def detect_max_resolution(cam):
    """Retourne (width, height) de la résolution maximale du capteur."""
    try:
        props = cam.camera_properties
        # Picamera2 expose PixelArraySize comme résolution native du capteur
        w, h = props["PixelArraySize"]
        return w, h
    except Exception:
        pass

    # Fallback : chercher dans les modes raw disponibles
    try:
        sensor_modes = cam.sensor_modes
        if sensor_modes:
            best = max(sensor_modes, key=lambda m: m["size"][0] * m["size"][1])
            return best["size"]
    except Exception:
        pass

    return 3280, 2464  # fallback sûr Module 2


def laplacian_variance(path: Path) -> float:
    """Variance du Laplacien — indicateur de netteté (plus élevé = plus net)."""
    try:
        import numpy as np
        from PIL import Image

        img = Image.open(path).convert("L")
        # Sous-échantillonnage pour la vitesse (1/4 de la taille)
        w, h = img.size
        img = img.resize((w // 4, h // 4), Image.LANCZOS)
        arr = np.array(img, dtype=np.float32)

        # Laplacien 3×3
        kernel = np.array([[0,  1,  0],
                            [1, -4,  1],
                            [0,  1,  0]], dtype=np.float32)
        from numpy.lib.stride_tricks import as_strided
        # Convolution manuelle (évite scipy)
        padded = np.pad(arr, 1, mode="reflect")
        lap = (padded[:-2, :-2] * kernel[0, 0]
             + padded[:-2, 1:-1] * kernel[0, 1]
             + padded[:-2, 2:]   * kernel[0, 2]
             + padded[1:-1, :-2] * kernel[1, 0]
             + padded[1:-1, 1:-1] * kernel[1, 1]
             + padded[1:-1, 2:]   * kernel[1, 2]
             + padded[2:, :-2]   * kernel[2, 0]
             + padded[2:, 1:-1]  * kernel[2, 1]
             + padded[2:, 2:]    * kernel[2, 2])
        return float(np.var(lap))
    except Exception:
        return -1.0


def print_exif(path: Path):
    """Affiche les données EXIF utiles si disponibles."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(path)
        exif = img._getexif()
        if not exif:
            print("   EXIF : aucune donnée")
            return
        wanted = {"ExposureTime", "ISOSpeedRatings", "FNumber",
                  "BrightnessValue", "WhiteBalance", "Flash"}
        found = {}
        for tag_id, val in exif.items():
            tag = TAGS.get(tag_id, str(tag_id))
            if tag in wanted:
                found[tag] = val
        if found:
            for k, v in found.items():
                # ExposureTime est souvent un tuple (num, den)
                if isinstance(v, tuple) and len(v) == 2:
                    v = f"{v[0]}/{v[1]}s"
                print(f"   {k:<18}: {v}")
        else:
            print("   EXIF : présent mais tags standards absents")
    except Exception as e:
        print(f"   EXIF : non disponible ({e})")


def capture_at(cam, out_path: Path, quality: int, label: str):
    """Capture une photo en still mode et retourne les métriques."""
    print(f"\n[{label}]")

    # Récupérer la résolution max depuis les propriétés du capteur
    max_w, max_h = detect_max_resolution(cam)

    # Still config à résolution maximale
    cfg = cam.create_still_configuration(
        main={"size": (max_w, max_h), "format": "RGB888"},
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_str = str(out_path)

    t0 = time.monotonic()
    cam.switch_mode_and_capture_file(cfg, out_str, quality=quality)
    elapsed = time.monotonic() - t0

    size_ko = out_path.stat().st_size / 1024
    size_mo = size_ko / 1024

    try:
        from PIL import Image
        img = Image.open(out_str)
        actual_w, actual_h = img.size
    except Exception:
        actual_w, actual_h = max_w, max_h

    sharpness = laplacian_variance(out_path)
    sharpness_str = f"{sharpness:.0f}" if sharpness >= 0 else "n/a"

    print(f"   Résolution : {actual_w} × {actual_h} px")
    print(f"   Taille     : {size_ko:.0f} Ko  ({size_mo:.2f} Mo)")
    print(f"   Temps      : {elapsed:.2f} s")
    print(f"   Netteté    : {sharpness_str}  (Laplacien, > 100 = bon)")
    print(f"   Fichier    : {out_path.name}")
    print_exif(out_path)

    return {"w": actual_w, "h": actual_h, "size_ko": size_ko,
            "time": elapsed, "sharpness": sharpness, "quality": quality,
            "path": out_path}


def main():
    print(SEP)
    print("  SnapForge — Test Qualité Photo (résolution maximale)")
    print(SEP)

    try:
        from picamera2 import Picamera2
    except ImportError:
        print("\nERREUR : Picamera2 introuvable.")
        print("Ce script nécessite un Raspberry Pi avec picamera2 installé.")
        print("  sudo apt install -y python3-picamera2")
        sys.exit(1)

    out_dir = ROOT / "Photo" / "test_quality"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nDossier de sortie : {out_dir.resolve()}")

    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  Initialisation de la caméra")
    print(SEP)

    cam = Picamera2()

    # Détection du capteur
    try:
        model = cam.camera_properties.get("Model", "inconnu")
        print(f"   Modèle capteur : {model}")
    except Exception:
        model = "inconnu"
        print("   Modèle capteur : non détecté")

    max_w, max_h = detect_max_resolution(cam)
    mpx = (max_w * max_h) / 1_000_000
    print(f"   Résolution max : {max_w} × {max_h}  ({mpx:.1f} Mpx)")

    # Démarrage en preview pour stabilisation AE/AWB
    print("\n   Démarrage preview (3s de stabilisation AE/AWB)...")
    preview_cfg = cam.create_preview_configuration(
        main={"size": (640, 480), "format": "RGB888"},
        raw={"size": (max_w, max_h)},
    )
    cam.configure(preview_cfg)
    cam.start()
    time.sleep(3.0)
    print("   Stabilisation terminée ✓")

    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  Captures de test")
    print(SEP)

    ts = time.strftime("%Y%m%d_%H%M%S")
    results = []

    # 3 captures : qualité 95, 85, 70
    configs = [
        (95, "qualite_95"),
        (85, "qualite_85"),
        (70, "qualite_70"),
    ]
    for quality, suffix in configs:
        fname = out_dir / f"test_{ts}_{suffix}.jpg"
        try:
            r = capture_at(cam, fname, quality, f"JPEG q={quality}")
            results.append(r)
            # Pause pour laisser l'AE se réadapter entre les captures
            time.sleep(1.5)
        except Exception as e:
            print(f"   ERREUR : {e}")

    cam.stop()
    cam.close()

    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  Synthèse")
    print(SEP)

    if results:
        print(f"\n   {'Qualité':>8}  {'Taille':>10}  {'Temps':>7}  {'Netteté':>10}")
        print(f"   {'-------':>8}  {'------':>10}  {'-----':>7}  {'-------':>10}")
        for r in results:
            sharp = f"{r['sharpness']:.0f}" if r['sharpness'] >= 0 else "n/a"
            print(f"   {r['quality']:>7}%  {r['size_ko']:>8.0f} Ko  "
                  f"{r['time']:>5.2f} s  {sharp:>10}")

        best = max((r for r in results if r['sharpness'] >= 0),
                   key=lambda r: r['sharpness'], default=None)
        if best:
            print(f"\n   Meilleure netteté : q={best['quality']}%  "
                  f"→ {best['path'].name}")

    print(f"\n   Photos dans : {out_dir.resolve()}")
    print(f"\n{SEP}")
    print("  Test terminé.")
    print(SEP)


if __name__ == "__main__":
    main()
