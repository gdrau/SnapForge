# SnapForge — PhotoBooth Raspberry Pi

Application photobooth moderne pour Raspberry Pi 4/5, compatible Raspberry Pi OS Bookworm.

**Stack :** Python 3.11 · Picamera2/libcamera · Pygame 2 · Pillow · gpiozero · rembg (IA optionnelle)

---

## Fonctionnalités

| Fonctionnalité        | MVP | V2 |
|-----------------------|:---:|:--:|
| Interface plein écran | ✅  |    |
| Écran tactile         | ✅  |    |
| Boutons physiques GPIO| ✅  |    |
| LEDs d'état           | ✅  |    |
| Caméra Pi v2 (Picamera2) | ✅ |  |
| 1, 2, 3 ou 4 photos   | ✅  |    |
| 2 templates de composition | ✅ |   |
| Compte à rebours + flash LED | ✅ | |
| QR code image finale  | ✅  |    |
| Démarrage auto (systemd) | ✅ |   |
| Mode hors ligne       | ✅  |    |
| Remplacement de fond IA | ✅ |   |
| Impression CUPS       | ✅  |    |
| Upload cloud          | ✅  |    |
| Google Photos         | ✅  |    |
| Cloudflare R2         | ✅  |    |
| Galerie locale        |     | ✅ |
| Interface admin       |     | ✅ |
| Suppression auto photos |   | ✅ |
| Mode événement        |     | ✅ |

---

## Démarrage rapide

```bash
git clone https://github.com/gdrau/SnapForge.git
cd SnapForge

# Créer la configuration locale
cp config.example.yaml config.yaml

# Créer l'environnement Python
# --system-site-packages permet d'accéder à picamera2 installé via apt
python3 -m venv venv --system-site-packages
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Lancer
python src/app.py
```

> **Développement sur PC** : `python src/app.py --windowed` — la caméra et les GPIO sont simulés automatiquement.

---

## Architecture

```
photobooth/
├── src/
│   ├── app.py                  # Point d'entrée
│   ├── config.py               # Chargement YAML
│   ├── state_machine.py        # Machine d'états (FSM)
│   ├── camera/
│   │   └── picamera2_camera.py # Picamera2 + mock dev
│   ├── ui/
│   │   └── pygame_ui.py        # Interface Pygame plein écran
│   ├── gpio/
│   │   ├── buttons.py          # Boutons physiques
│   │   └── lights.py           # LEDs
│   ├── processing/
│   │   ├── composer.py         # Composition image finale
│   │   └── ai_background.py    # rembg / mediapipe / remove.bg
│   ├── cloud/
│   │   ├── base.py             # Interface abstraite
│   │   ├── local.py            # Copie locale
│   │   ├── google_photos.py    # Google Photos
│   │   ├── cloudflare.py       # Cloudflare R2
│   │   └── uploader.py         # Gestionnaire + file d'attente
│   ├── qr/
│   │   └── qr_generator.py     # QR code
│   └── print/
│       └── cups_printer.py     # CUPS
├── templates/
│   ├── strip_classic.json      # Bande 4 photos
│   └── dark_collage.json       # Grille 2×2
├── assets/
│   ├── backgrounds/            # Fonds pour l'IA
│   ├── overlays/               # PNG à superposer aux templates
│   └── fonts/                  # Police TTF (optionnelle)
├── docs/
│   ├── INSTALLATION.md
│   ├── GPIO_WIRING.md
│   ├── TEMPLATES.md
│   └── TESTING.md
├── scripts/
│   ├── test_gpio.py
│   ├── test_camera.py
│   ├── test_qr.py
│   └── test_ai.py
├── config.example.yaml
├── photobooth.service          # Service systemd
└── requirements.txt
```

---

## Machine d'états

```
IDLE → CHOOSE_FORMAT → PREVIEW → COUNTDOWN → CAPTURE
                                    ↑              ↓ (si photos restantes)
                                    └──────────────┘
                                    ↓ (toutes prises)
                               PROCESSING → REVIEW → PRINT_WAIT ─┐
                                                ↓                 │
                                           UPLOADING ←────────────┘
                                                ↓
                                           QR_DISPLAY → IDLE
```

---

## GPIO (brochage physique / BOARD)

| Rôle              | Pin physique | BCM |
|-------------------|:------------:|:---:|
| Bouton photo      | 11           | 17  |
| LED photo         | 7            | 4   |
| Bouton print      | 13           | 27  |
| LED print         | 15           | 22  |
| LED startup       | 29           | 5   |
| LED séquence      | 31           | 6   |
| LED flash         | 33           | 13  |

Voir [docs/GPIO_WIRING.md](docs/GPIO_WIRING.md) pour le schéma détaillé.

---

## IA — Remplacement de fond

Trois providers disponibles dans `config.yaml` :

| Provider       | Qualité  | Vitesse (Pi 4) | Internet | Coût   |
|----------------|----------|:--------------:|:--------:|--------|
| `rembg`        | ⭐⭐⭐⭐  | ~4-8s          | Non      | Gratuit|
| `mediapipe`    | ⭐⭐⭐    | <1s            | Non      | Gratuit|
| `removebg_api` | ⭐⭐⭐⭐⭐ | ~2s            | Oui      | 50/mois gratuit |

**Recommandé : `rembg`** — meilleur compromis qualité/autonomie pour photobooth.

---

## Documentation

- [Installation complète](docs/INSTALLATION.md)
- [Câblage GPIO](docs/GPIO_WIRING.md)
- [Créer un template](docs/TEMPLATES.md)
- [Procédures de test](docs/TESTING.md)
