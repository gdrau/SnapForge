#!/usr/bin/env python3
"""
test_preview.py — Preview interactif pour réglage focus et qualité image.
Lancer sur le Raspberry Pi (l'application principale doit être arrêtée).

  TAB       → basculer mode  Focus ↔ Qualité
  ESPACE    → capturer photo test  → Photo/tests/preview_test.jpg
  R         → remettre les réglages à zéro (valeurs config.yaml)
  ESC / Q   → quitter

Mode Focus :
  ↑ / ↓    → LensPosition  (mise au point manuelle, pas de 0.1)
  A         → autofocus ponctuel  (AfTrigger)
  C         → autofocus continu   (AfMode continu)
  M         → repasser en mode manuel

Mode Qualité :
  ← / →    → sélectionner le réglage
  ↑ / ↓    → augmenter / diminuer la valeur
"""

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

# ── Configuration ────────────────────────────────────────────────────────────
try:
    from config import load_config, Config
    cfg = Config(load_config())
except Exception:
    cfg = None

def _cfg(key, default):
    return cfg.get(key, default) if cfg else default

PW = _cfg("camera.preview_width",  640)
PH = _cfg("camera.preview_height", 480)
CW = _cfg("camera.resolution_width",  3280)
CH = _cfg("camera.resolution_height", 2464)
FLIP_H = int(_cfg("camera.flip_horizontal", False))
FLIP_V = int(_cfg("camera.flip_vertical",   False))

# Defaults from config (used by Reset)
DEF = {
    "sharpness":  float(_cfg("camera.sharpness",   1.0)),
    "contrast":   float(_cfg("camera.contrast",    1.0)),
    "saturation": float(_cfg("camera.saturation",  1.0)),
    "brightness": float(_cfg("camera.brightness",  0.0)),
    "ev":         float(_cfg("camera.exposure_value", 0.0)),
    "nr_mode":    int  (_cfg("camera.noise_reduction_mode", 1)),
    "lens_pos":   1.0,
}

# ── Picamera2 ─────────────────────────────────────────────────────────────────
try:
    from picamera2 import Picamera2
except ImportError:
    print("ERREUR : Picamera2 non disponible. Ce script doit être lancé sur le Pi.")
    sys.exit(1)

try:
    import libcamera
    transform = libcamera.Transform(hflip=FLIP_H, vflip=FLIP_V) if (FLIP_H or FLIP_V) else None
except ImportError:
    transform = None

cam = Picamera2()
cfg_kwargs = {"transform": transform} if transform else {}
preview_cfg = cam.create_preview_configuration(
    main={"size": (PW, PH), "format": "RGB888"},
    **cfg_kwargs,
)
cam.configure(preview_cfg)
cam.start()
time.sleep(2.0)

# ── ISO fixé à 100 (test) ─────────────────────────────────────────────────────
# AeEnable=False désactive l'exposition auto pour figer le gain à 1.0 (≈ ISO 100)
# ExposureTime en µs — adapter si l'image est trop sombre/claire (ex: 20000 = 1/50s)
cam.set_controls({
    "AeEnable":     False,
    "AnalogueGain": 1.0,
    "ExposureTime": 20000,   # 1/50s — modifier selon la luminosité
})
print("ISO 100 fixé (AeEnable=False, AnalogueGain=1.0, ExposureTime=20000µs)")

# ── Pygame ────────────────────────────────────────────────────────────────────
import pygame
import numpy as np

pygame.init()
WIN_W, WIN_H = max(PW, 800), max(PH + 200, 680)
screen = pygame.display.set_mode((WIN_W, WIN_H))
pygame.display.set_caption("SnapForge — Réglage caméra")
clock = pygame.time.Clock()

FONT_LG = pygame.font.SysFont("monospace", 22, bold=True)
FONT_MD = pygame.font.SysFont("monospace", 17)
FONT_SM = pygame.font.SysFont("monospace", 14)

C_BG     = (22,  27,  34)
C_PANEL  = (36,  41,  50)
C_SEL    = (255, 165,  0)
C_WHITE  = (255, 255, 255)
C_GRAY   = (120, 130, 140)
C_GREEN  = (60,  200,  80)
C_BLUE   = (80,  160, 255)
C_RED    = (220,  60,  60)

# ── État partagé ──────────────────────────────────────────────────────────────
_lock        = threading.Lock()
_last_frame  = None          # numpy array RGB

def _preview_loop():
    global _last_frame
    while _running:
        try:
            frame = cam.capture_array()
            if frame is not None and frame.ndim == 3:
                frame = frame[:, :, ::-1].copy()   # BGR → RGB
            with _lock:
                _last_frame = frame
        except Exception:
            time.sleep(0.05)

_running = True
threading.Thread(target=_preview_loop, daemon=True).start()

# ── Réglages courants ─────────────────────────────────────────────────────────
state = dict(DEF)
mode  = "focus"   # "focus" | "quality"
quality_sel = 0   # index du réglage sélectionné en mode qualité

# Méta-descripteur des réglages qualité
QUALITY_PARAMS = [
    {"key": "sharpness",  "label": "Netteté",    "min": 0.0,  "max": 16.0, "step": 0.1,  "fmt": ".1f"},
    {"key": "contrast",   "label": "Contraste",  "min": 0.5,  "max": 2.0,  "step": 0.05, "fmt": ".2f"},
    {"key": "saturation", "label": "Saturation", "min": 0.0,  "max": 2.0,  "step": 0.1,  "fmt": ".1f"},
    {"key": "brightness", "label": "Luminosité", "min": -1.0, "max": 1.0,  "step": 0.05, "fmt": ".2f"},
    {"key": "ev",         "label": "EV",         "min": -4.0, "max": 4.0,  "step": 0.25, "fmt": ".2f"},
    {"key": "nr_mode",    "label": "Débruitage", "min": 0,    "max": 2,    "step": 1,    "fmt": "int"},
]
NR_LABELS = {0: "DÉSACTIVÉ", 1: "RAPIDE", 2: "HAUTE QUALITÉ"}

af_mode_label = "Manuel"
last_msg      = ""
msg_until     = 0.0
out_dir       = ROOT / "Photo" / "tests"
out_dir.mkdir(parents=True, exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def apply_quality():
    ctrl = {
        "Sharpness":          state["sharpness"],
        "Contrast":           state["contrast"],
        "Saturation":         state["saturation"],
        "Brightness":         state["brightness"],
        "ExposureValue":      state["ev"],
        "NoiseReductionMode": state["nr_mode"],
    }
    try:
        cam.set_controls(ctrl)
    except Exception as e:
        set_msg(f"Erreur contrôle : {e}", C_RED)

def apply_lens():
    try:
        cam.set_controls({"AfMode": 0, "LensPosition": state["lens_pos"]})
    except Exception as e:
        set_msg(f"Focus non supporté : {e}", C_RED)

def set_msg(text, color=C_GREEN):
    global last_msg, msg_until, msg_color
    last_msg = text
    msg_color = color
    msg_until = time.time() + 3.0

msg_color = C_GREEN

def txt(surface, text, font, color, x, y, center=False):
    s = font.render(str(text), True, color)
    if center:
        x -= s.get_width() // 2
    surface.blit(s, (x, y))
    return s.get_height()

def fmt_val(p, val):
    if p["fmt"] == "int":
        return NR_LABELS.get(int(val), str(int(val)))
    return f"{val:{p['fmt']}}"

# ── Boucle principale ─────────────────────────────────────────────────────────
apply_quality()
running = True

while running:
    clock.tick(30)

    # ── Événements ──────────────────────────────────────────────────────────
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            k = event.key

            if k in (pygame.K_ESCAPE, pygame.K_q):
                running = False

            elif k == pygame.K_TAB:
                mode = "quality" if mode == "focus" else "focus"

            elif k == pygame.K_r:
                state = dict(DEF)
                apply_quality()
                apply_lens()
                set_msg("Réglages remis à zéro")

            elif k == pygame.K_SPACE:
                out = str(out_dir / f"preview_test_{int(time.time())}.jpg")
                try:
                    _running = False
                    time.sleep(0.15)
                    still_kwargs = {"transform": transform} if transform else {}
                    still_cfg = cam.create_still_configuration(
                        main={"size": (CW, CH), "format": "RGB888"},
                        **still_kwargs,
                    )
                    cam.switch_mode_and_capture_file(still_cfg, out)
                    # Retour preview
                    cam.configure(preview_cfg)
                    cam.start()
                    time.sleep(0.5)
                    _running = True
                    threading.Thread(target=_preview_loop, daemon=True).start()
                    size_kb = Path(out).stat().st_size // 1024
                    set_msg(f"Photo sauvegardée ({size_kb} Ko) → {Path(out).name}")
                except Exception as e:
                    _running = True
                    threading.Thread(target=_preview_loop, daemon=True).start()
                    set_msg(f"Capture échouée : {e}", C_RED)

            # ── Mode Focus ─────────────────────────────────────────────────
            elif mode == "focus":
                if k == pygame.K_UP:
                    state["lens_pos"] = round(min(10.0, state["lens_pos"] + 0.1), 2)
                    apply_lens()
                elif k == pygame.K_DOWN:
                    state["lens_pos"] = round(max(0.0, state["lens_pos"] - 0.1), 2)
                    apply_lens()
                elif k == pygame.K_a:
                    try:
                        cam.set_controls({"AfMode": 1, "AfTrigger": 0})
                        af_mode_label = "AF ponctuel"
                        set_msg("Autofocus déclenché")
                    except Exception as e:
                        set_msg(f"AF non supporté : {e}", C_RED)
                elif k == pygame.K_c:
                    try:
                        cam.set_controls({"AfMode": 2})
                        af_mode_label = "AF continu"
                        set_msg("Autofocus continu activé")
                    except Exception as e:
                        set_msg(f"AF non supporté : {e}", C_RED)
                elif k == pygame.K_m:
                    af_mode_label = "Manuel"
                    apply_lens()
                    set_msg("Mode manuel")

            # ── Mode Qualité ───────────────────────────────────────────────
            elif mode == "quality":
                if k == pygame.K_LEFT:
                    quality_sel = (quality_sel - 1) % len(QUALITY_PARAMS)
                elif k == pygame.K_RIGHT:
                    quality_sel = (quality_sel + 1) % len(QUALITY_PARAMS)
                elif k in (pygame.K_UP, pygame.K_DOWN):
                    p = QUALITY_PARAMS[quality_sel]
                    delta = p["step"] if k == pygame.K_UP else -p["step"]
                    if p["fmt"] == "int":
                        new_val = int(round(state[p["key"]] + delta))
                    else:
                        new_val = round(state[p["key"]] + delta, 4)
                    state[p["key"]] = max(p["min"], min(p["max"], new_val))
                    apply_quality()

    # ── Rendu ────────────────────────────────────────────────────────────────
    screen.fill(C_BG)

    # Preview caméra
    with _lock:
        frame = _last_frame
    if frame is not None:
        try:
            surf = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
            # Mise à l'échelle en conservant le ratio
            scale = min(WIN_W / frame.shape[1], (WIN_H - 200) / frame.shape[0])
            sw = int(frame.shape[1] * scale)
            sh = int(frame.shape[0] * scale)
            surf = pygame.transform.scale(surf, (sw, sh))
            screen.blit(surf, ((WIN_W - sw) // 2, 0))
        except Exception:
            pass

    # Panneau inférieur
    panel_y = WIN_H - 200
    pygame.draw.rect(screen, C_PANEL, (0, panel_y, WIN_W, 200))
    pygame.draw.line(screen, C_SEL if mode == "focus" else C_BLUE,
                     (0, panel_y), (WIN_W, panel_y), 2)

    # Titre du mode
    mode_lbl = "◉ MODE FOCUS" if mode == "focus" else "◉ MODE QUALITÉ"
    mode_col = C_SEL if mode == "focus" else C_BLUE
    txt(screen, mode_lbl, FONT_LG, mode_col, 16, panel_y + 8)
    txt(screen, "TAB pour changer de mode", FONT_SM, C_GRAY, WIN_W - 220, panel_y + 12)

    y = panel_y + 38

    if mode == "focus":
        # Ligne 1 : LensPosition
        txt(screen, f"LensPosition : {state['lens_pos']:.1f}", FONT_MD, C_WHITE, 16, y)
        txt(screen, f"Mode AF : {af_mode_label}", FONT_MD, C_GRAY, 280, y)
        y += 26
        # Ligne 2 : aide touches
        txt(screen, "↑/↓ Focus   A=AF ponctuel   C=AF continu   M=Manuel", FONT_SM, C_GRAY, 16, y)
        y += 22
        txt(screen, "0.0 = infini        valeurs élevées = proche", FONT_SM, C_GRAY, 16, y)

    else:
        # Grille des paramètres qualité : 3 par ligne
        cols = 3
        col_w = (WIN_W - 32) // cols
        for i, p in enumerate(QUALITY_PARAMS):
            col = i % cols
            row = i // cols
            px = 16 + col * col_w
            py = y + row * 38
            is_sel = (i == quality_sel)
            bg_col = (50, 55, 70) if is_sel else C_PANEL
            pygame.draw.rect(screen, bg_col, (px - 4, py - 4, col_w - 8, 34), border_radius=6)
            if is_sel:
                pygame.draw.rect(screen, C_BLUE, (px - 4, py - 4, col_w - 8, 34), 2, border_radius=6)
            prefix = "► " if is_sel else "  "
            label_col = C_WHITE if is_sel else C_GRAY
            val_col   = C_SEL   if is_sel else C_WHITE
            txt(screen, prefix + p["label"], FONT_SM, label_col, px, py)
            txt(screen, fmt_val(p, state[p["key"]]), FONT_MD, val_col, px + col_w - 90, py - 2)

        y += (len(QUALITY_PARAMS) // cols + 1) * 38 + 4
        txt(screen, "←/→ Sélectionner   ↑/↓ Régler", FONT_SM, C_GRAY, 16, y)

    # Message flash
    if time.time() < msg_until:
        msg_surf = FONT_MD.render(last_msg, True, msg_color)
        mx = (WIN_W - msg_surf.get_width()) // 2
        screen.blit(msg_surf, (mx, WIN_H - 28))

    # Raccourcis permanents
    hints = "ESPACE = photo test    R = reset    ESC = quitter"
    txt(screen, hints, FONT_SM, C_GRAY, WIN_W // 2, WIN_H - 28
        if time.time() >= msg_until else WIN_H - 46, center=True)

    pygame.display.flip()

# ── Nettoyage ─────────────────────────────────────────────────────────────────
_running = False
time.sleep(0.2)
cam.stop()
cam.close()
pygame.quit()
print(f"Photos de test dans : {out_dir.resolve()}")
