#!/usr/bin/env python3
"""
Test caméra SnapForge — réglage mise au point et cadrage.
Lit config.yaml automatiquement si présent.

  ESPACE  →  photo test haute résolution  (/tmp/test_focus_XX.jpg)
  Q / ESC →  quitter
"""
import sys
import time
import threading
from pathlib import Path

try:
    import pygame
    import numpy as np
    from picamera2 import Picamera2
except ImportError as e:
    print(f"Dépendance manquante : {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Lecture config.yaml optionnelle
# ---------------------------------------------------------------------------
_raw_cfg: dict = {}
try:
    import yaml
    p = Path("config.yaml")
    if p.exists():
        _raw_cfg = yaml.safe_load(p.read_text()) or {}
        print("config.yaml chargé")
    else:
        print("config.yaml absent — valeurs par défaut")
except Exception as exc:
    print(f"Impossible de lire config.yaml : {exc}")

def _get(key: str, default):
    d = _raw_cfg
    for part in key.split("."):
        if not isinstance(d, dict):
            return default
        d = d.get(part, {})
    return d if d != {} else default

PREV_W = _get("camera.preview_width",    640)
PREV_H = _get("camera.preview_height",   480)
CAP_W  = _get("camera.resolution_width",  3280)
CAP_H  = _get("camera.resolution_height", 2464)
FLIP_H = int(_get("camera.flip_horizontal", False))
FLIP_V = int(_get("camera.flip_vertical",   False))
NR     = int(_get("camera.noise_reduction_mode", 1))
SHARP  = float(_get("camera.sharpness", 1.0))

SCREEN_W, SCREEN_H = 800, 480
OUTPUT_DIR = Path("/tmp")

# ---------------------------------------------------------------------------
# Initialisation caméra
# ---------------------------------------------------------------------------
print(f"Démarrage Picamera2  prév.={PREV_W}×{PREV_H}  cap.={CAP_W}×{CAP_H}")
cam = Picamera2()

_transform = None
if FLIP_H or FLIP_V:
    import libcamera
    _transform = libcamera.Transform(hflip=FLIP_H, vflip=FLIP_V)

_tk = {"transform": _transform} if _transform else {}

prev_cfg = cam.create_preview_configuration(
    main={"size": (PREV_W, PREV_H), "format": "RGB888"},
    raw={"size": (CAP_W, CAP_H)},
    **_tk,
)
cam.configure(prev_cfg)
cam.start()

controls = {"NoiseReductionMode": NR}
if SHARP != 1.0:
    controls["Sharpness"] = SHARP
try:
    cam.set_controls(controls)
except Exception as e:
    print(f"Contrôles ISP non supportés : {e}")

time.sleep(1.5)
print("Caméra prête")

# ---------------------------------------------------------------------------
# Pygame
# ---------------------------------------------------------------------------
pygame.init()
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
pygame.display.set_caption("Test camera SnapForge — ESPACE=capture  Q=quitter")
pygame.display.set_allow_screensaver(False)   # empêche pygame d'activer l'économiseur

# Désactiver le blanking écran X11 (Pi OS desktop)
import subprocess as _sp
for _cmd in (["xset", "s", "off"], ["xset", "-dpms"], ["xset", "s", "noblank"]):
    try:
        _sp.run(_cmd, check=False, capture_output=True)
    except Exception:
        pass

font_sm  = pygame.font.SysFont("monospace", 16)
font_big = pygame.font.SysFont("monospace", 20, bold=True)
clock    = pygame.time.Clock()

# ---------------------------------------------------------------------------
# Boucle de capture preview (thread)
# ---------------------------------------------------------------------------
_frame_lock  = threading.Lock()
_latest      = [None]
_paused      = threading.Event()

def _preview_loop():
    while True:
        if _paused.is_set():
            time.sleep(0.02)
            continue
        try:
            f = cam.capture_array()
            if f is not None and f.ndim == 3 and f.shape[2] == 3:
                with _frame_lock:
                    _latest[0] = f
            time.sleep(1 / 30)   # limiter à 30 fps, évite de saturer picamera2
        except Exception as e:
            print(f"[preview] erreur: {e}")
            time.sleep(0.1)

threading.Thread(target=_preview_loop, daemon=True).start()

# ---------------------------------------------------------------------------
# Guides de cadrage
# ---------------------------------------------------------------------------
def _draw_guides(surface, w, h):
    c_grid   = (0, 200, 100)
    c_center = (255, 80, 80)
    # Règle des tiers
    for t in (1/3, 2/3):
        pygame.draw.line(surface, c_grid, (int(w * t), 0), (int(w * t), h), 1)
        pygame.draw.line(surface, c_grid, (0, int(h * t)), (w, int(h * t)), 1)
    # Viseur central
    cx, cy, r = w // 2, h // 2, 28
    pygame.draw.circle(surface, c_center, (cx, cy), r, 1)
    pygame.draw.line(surface, c_center, (cx - 55, cy), (cx - r - 4, cy), 1)
    pygame.draw.line(surface, c_center, (cx + r + 4, cy), (cx + 55, cy), 1)
    pygame.draw.line(surface, c_center, (cx, cy - 55), (cx, cy - r - 4), 1)
    pygame.draw.line(surface, c_center, (cx, cy + r + 4), (cx, cy + 55), 1)

# ---------------------------------------------------------------------------
# Capture haute résolution
# ---------------------------------------------------------------------------
_counter = [1]

def _do_capture():
    _paused.set()
    time.sleep(0.05)
    still_cfg = cam.create_still_configuration(
        main={"size": (CAP_W, CAP_H), "format": "RGB888"},
        **_tk,
    )
    out = str(OUTPUT_DIR / f"test_focus_{_counter[0]:02d}.jpg")
    try:
        cam.switch_mode_and_capture_file(still_cfg, out)
        _counter[0] += 1
        print(f"Photo : {out}")
        return out
    except Exception as e:
        print(f"Erreur capture : {e}")
        return None
    finally:
        _paused.clear()

# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------
_msg       = [""]
_msg_timer = [0]

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pass   # ignorer — fermeture uniquement via Q/ESC (évite l'arrêt par l'OS)
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_q, pygame.K_ESCAPE):
                running = False
            elif event.key == pygame.K_SPACE and not _paused.is_set():
                out = _do_capture()
                if out:
                    _msg[0] = f"OK -> {out}"
                    _msg_timer[0] = 180
                else:
                    _msg[0] = "Erreur capture"
                    _msg_timer[0] = 120

    with _frame_lock:
        frame = _latest[0]

    screen.fill((15, 15, 15))

    if frame is not None:
        try:
            surf = pygame.surfarray.make_surface(frame.transpose(1, 0, 2))
            fw, fh = surf.get_size()
            ratio = min(SCREEN_W / fw, (SCREEN_H - 44) / fh)
            nw, nh = int(fw * ratio), int(fh * ratio)
            surf  = pygame.transform.scale(surf, (nw, nh))
            ox    = (SCREEN_W - nw) // 2
            oy    = ((SCREEN_H - 44) - nh) // 2
            screen.blit(surf, (ox, oy))

            gs = pygame.Surface((nw, nh), pygame.SRCALPHA)
            _draw_guides(gs, nw, nh)
            screen.blit(gs, (ox, oy))
        except Exception as e:
            print(f"[display] erreur frame: {e}")

    # Bandeau bas
    pygame.draw.rect(screen, (30, 30, 30), (0, SCREEN_H - 44, SCREEN_W, 44))
    info = font_sm.render(
        f"Prev {PREV_W}x{PREV_H}  |  Cap {CAP_W}x{CAP_H}  |  NR:{NR}  Sharp:{SHARP}  flipH:{bool(FLIP_H)}",
        True, (160, 160, 160),
    )
    hint = font_sm.render(
        "ESPACE = photo test   Q / ESC = quitter",
        True, (100, 100, 100),
    )
    screen.blit(info, (10, SCREEN_H - 42))
    screen.blit(hint, (10, SCREEN_H - 22))

    if _msg_timer[0] > 0:
        label = font_big.render(_msg[0], True, (60, 220, 80))
        bg    = pygame.Surface((label.get_width() + 16, label.get_height() + 8))
        bg.fill((20, 20, 20))
        screen.blit(bg, (8, 8))
        screen.blit(label, (16, 12))
        _msg_timer[0] -= 1

    pygame.display.flip()
    clock.tick(30)

cam.stop()
cam.close()
pygame.quit()
print("Terminé.")
