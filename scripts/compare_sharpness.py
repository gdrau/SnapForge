#!/usr/bin/env python3
"""Compare objectivement deux photos (netteté, bruit, contraste, couleur).

Usage :
    python scripts/compare_sharpness.py IMAGE_A.jpg IMAGE_B.jpg
    python scripts/compare_sharpness.py snapforge.jpg pibooth.jpg

Sert à comparer une capture SnapForge (libcamera) à une capture pibooth (legacy)
pour savoir laquelle est réellement la plus nette, et de combien.

Métriques :
  - Laplacian variance   : proxy de netteté (plus haut = plus net)
  - High-freq energy      : énergie des hautes fréquences (détail fin réel)
  - Contraste (std luma)  : écart-type de la luminance
  - Black point (p1)      : niveau des noirs (percentile 1)
  - White point (p99)     : niveau des blancs (percentile 99)
  - Dominante couleur     : moyenne R/G/B sur les zones neutres (gray-world)

Pour une comparaison JUSTE, les deux images sont ramenées à la même hauteur
avant le calcul de netteté (sinon la résolution fausse tout).
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def luminance(arr: np.ndarray) -> np.ndarray:
    """arr HxWx3 uint8 -> HxW float luma (Rec.601)."""
    return (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2])


def laplacian_var(luma: np.ndarray) -> float:
    """Variance du Laplacien 3x3 — proxy classique de netteté."""
    k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)
    h, w = luma.shape
    out = np.zeros((h - 2, w - 2), dtype=np.float64)
    for dy in range(3):
        for dx in range(3):
            out += k[dy, dx] * luma[dy:dy + h - 2, dx:dx + w - 2]
    return float(out.var())


def high_freq_energy(luma: np.ndarray) -> float:
    """Ratio d'énergie dans les hautes fréquences (FFT). Détail fin réel."""
    f = np.fft.fftshift(np.abs(np.fft.fft2(luma)))
    h, w = luma.shape
    cy, cx = h // 2, w // 2
    total = f.sum() + 1e-9
    # masque basses fréquences : disque central de rayon 1/8
    r = min(h, w) // 8
    yy, xx = np.ogrid[:h, :w]
    low_mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r
    low = f[low_mask].sum()
    return float((total - low) / total)


def color_cast(arr: np.ndarray):
    """Moyenne R/G/B sur pixels quasi-neutres (gray-world). Détecte la dominante."""
    r, g, b = arr[:, :, 0].astype(float), arr[:, :, 1].astype(float), arr[:, :, 2].astype(float)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    # zones quasi-neutres et mi-tons (évite noir/blanc purs)
    neutral = (mx - mn < 40) & (mx > 60) & (mx < 230)
    if neutral.sum() < 100:
        neutral = np.ones(r.shape, dtype=bool)
    return (float(r[neutral].mean()), float(g[neutral].mean()), float(b[neutral].mean()))


def analyze(path: str, norm_height: int = 1600) -> dict:
    img = Image.open(path).convert("RGB")
    w0, h0 = img.size
    arr_full = np.asarray(img)

    # Version normalisée en hauteur pour une netteté comparable
    if h0 != norm_height:
        nw = int(w0 * norm_height / h0)
        img_n = img.resize((nw, norm_height), Image.LANCZOS)
    else:
        img_n = img
    arr_n = np.asarray(img_n)
    luma_n = luminance(arr_n)

    r, g, b = color_cast(arr_full)
    luma_full = luminance(arr_full)
    return {
        "path": Path(path).name,
        "size": (w0, h0),
        "mpx": round(w0 * h0 / 1e6, 1),
        "lap_var_norm": laplacian_var(luma_n),
        "hf_energy": high_freq_energy(luma_n),
        "contrast_std": float(luma_full.std()),
        "black_p1": float(np.percentile(luma_full, 1)),
        "white_p99": float(np.percentile(luma_full, 99)),
        "rgb_neutral": (round(r, 1), round(g, 1), round(b, 1)),
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    a = analyze(sys.argv[1])
    b = analyze(sys.argv[2])

    def row(label, ka, kb, fmt="{:.1f}", higher_better=None):
        va, vb = a[ka], b[kb] if False else b[ka]
        sa, sb = fmt.format(va), fmt.format(vb)
        note = ""
        if higher_better is not None and va and vb:
            ratio = va / vb if vb else 0
            winner = a["path"] if (va > vb) == higher_better else b["path"]
            note = f"  -> {winner} ({'x%.2f' % (max(va, vb) / max(min(va, vb), 1e-9))})"
        print(f"  {label:22} {sa:>14} {sb:>14}{note}")

    print(f"\n{'':22} {a['path']:>14} {b['path']:>14}")
    print("  " + "-" * 52)
    print(f"  {'Résolution':22} {str(a['size']):>14} {str(b['size']):>14}")
    print(f"  {'Mégapixels':22} {a['mpx']:>14} {b['mpx']:>14}")
    row("Netteté (Laplacian)", "lap_var_norm", None, "{:.0f}", higher_better=True)
    row("Détail HF (0-1)", "hf_energy", None, "{:.4f}", higher_better=True)
    row("Contraste (std)", "contrast_std", None, "{:.1f}", higher_better=True)
    row("Noirs (p1, bas=mieux)", "black_p1", None, "{:.1f}", higher_better=False)
    row("Blancs (p99)", "white_p99", None, "{:.1f}")
    print(f"  {'RGB neutre (cast)':22} {str(a['rgb_neutral']):>14} {str(b['rgb_neutral']):>14}")
    print()
    # Diagnostic couleur
    for res in (a, b):
        r, g, b_ = res["rgb_neutral"]
        avg = (r + g + b_) / 3
        casts = []
        if g > avg + 3: casts.append("vert")
        if r > avg + 3: casts.append("rouge/chaud")
        if b_ > avg + 3: casts.append("bleu/froid")
        if r < avg - 3 and g < avg - 3: casts.append("(manque de chaud)")
        print(f"  Dominante {res['path']:20}: {', '.join(casts) or 'neutre'}")
    print()


if __name__ == "__main__":
    main()
