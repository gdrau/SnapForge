# SnapForge — PhotoBooth Raspberry Pi

Application photobooth moderne pour Raspberry Pi 4/5, compatible **Raspberry Pi OS Trixie 64-bit**.

**Stack :** Python 3.13 · Picamera2/libcamera · Pygame 2 · Pillow · gpiozero · rembg (IA optionnelle)

---

## Fonctionnalités

| Fonctionnalité                  | MVP | V2 |
|---------------------------------|:---:|:--:|
| Interface plein écran           | ✅  |    |
| Écran tactile + boutons physiques | ✅ |   |
| LEDs d'état GPIO                | ✅  |    |
| Caméra Pi v2 (Picamera2)        | ✅  |    |
| Choix format 1 ou 4 photos (configurable) | ✅ | |
| Templates 10×15 cm portrait/paysage | ✅ |  |
| Titre & description personnalisables | ✅ |  |
| Police personnalisable (TTF)    | ✅  |    |
| Compte à rebours + flash LED    | ✅  |    |
| QR code image finale            | ✅  |    |
| Démarrage auto (systemd)        | ✅  |    |
| Mode hors ligne                 | ✅  |    |
| Menu admin complet (sous-menus) | ✅  |    |
| Navigation clavier admin        | ✅  |    |
| Remplacement de fond IA         | ✅  |    |
| Impression CUPS                 | ✅  |    |
| Upload cloud (Google, Cloudflare) | ✅ |   |
| Galerie locale consultable      |     | ✅ |
| Interface admin web             |     | ✅ |

---

## Démarrage rapide

```bash
git clone https://github.com/gdrau/SnapForge.git
cd SnapForge
cp config.example.yaml config.yaml

# --system-site-packages donne accès à picamera2 installé via apt
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install -r requirements.txt

# Lancer (mode fenêtré sur PC, la caméra et GPIO sont simulés)
python src/app.py --windowed
```

---

## Architecture

```
SnapForge/
├── src/
│   ├── app.py                  # Point d'entrée
│   ├── config.py               # Chargement YAML + backup sauvegarde
│   ├── state_machine.py        # Machine d'états (FSM 11 états)
│   ├── camera/
│   │   └── picamera2_camera.py # Picamera2 réelle + simulée (PC)
│   ├── ui/
│   │   └── pygame_ui.py        # Interface Pygame plein écran
│   ├── gpio/
│   │   ├── buttons.py          # Boutons (bounce 50ms)
│   │   └── lights.py           # LEDs avec clignotement
│   ├── processing/
│   │   ├── composer.py         # Composition par template JSON
│   │   ├── ai_background.py    # rembg / mediapipe / remove.bg
│   │   └── background_gen.py   # Générateur fond par défaut
│   ├── cloud/
│   │   ├── base.py             # Interface abstraite
│   │   ├── local.py            # Copie locale
│   │   ├── google_photos.py    # Google Photos OAuth2
│   │   ├── cloudflare.py       # Cloudflare R2
│   │   └── uploader.py         # Gestionnaire + file d'attente JSON
│   ├── qr/
│   │   └── qr_generator.py     # QR code PIL
│   └── print/
│       └── cups_printer.py     # CUPS via lp
├── templates/
│   ├── portrait_1photo.json    # 1181×1772 px (10×15 cm portrait)
│   └── landscape_4photos.json  # 1772×1181 px (15×10 cm paysage)
├── assets/
│   ├── fonts/                  # Polices TTF (ex: Montserrat-Regular.ttf)
│   ├── backgrounds/            # Fonds pour IA et templates
│   └── overlays/               # PNG RGBA superposés aux templates
├── docs/
│   ├── INSTALLATION.md
│   ├── GPIO_WIRING.md
│   ├── TEMPLATES.md
│   ├── TESTING.md
│   └── Create_Update_Git_Raspberry.md
├── scripts/
│   ├── test_gpio.py
│   ├── test_camera.py
│   ├── test_qr.py
│   └── test_ai.py
├── config.example.yaml
├── snapforge.service           # Service systemd
└── requirements.txt
```

---

## Machine d'états

```
IDLE → CHOOSE_FORMAT → PREVIEW → COUNTDOWN → CAPTURE
                                    ↑              ↓ (photos restantes)
                                    └──────────────┘
                                    ↓ (série complète)
                               PROCESSING → REVIEW (si impression)
                                    ↓
                               QR_DISPLAY ──────────────────→ IDLE
```

> Sans imprimante : PROCESSING → QR_DISPLAY directement (upload en arrière-plan).

---

## GPIO (brochage physique / BOARD)

| Rôle              | Pin physique | BCM |
|-------------------|:------------:|:---:|
| Bouton 1 (photo)  | 11           | 17  |
| LED photo         | 7            | 4   |
| Bouton 2 (print)  | 13           | 27  |
| LED print         | 15           | 22  |
| LED startup       | 29           | 5   |
| LED séquence      | 31           | 6   |
| LED flash         | 33           | 13  |

Voir [docs/GPIO_WIRING.md](docs/GPIO_WIRING.md) pour le schéma détaillé.

---

## Menu administration (touche ESC)

Structure en sous-menus, navigable au clavier :

```
ADMINISTRATION
├── Plugins           QR Code · IA · Impression · Upload
├── Photos/Templates  Formats · Templates · Titre · Description
├── Configuration     Nom du photobooth · Délai
├── Diagnostic GPIO   Boutons · LEDs · Journal
└── Sauvegarder / Quitter
```

**Navigation clavier :**

| Touche | Action |
|--------|--------|
| `↓` / `↑` | Item suivant / précédent (sans wrap) |
| `→` ou `Entrée` | Ouvrir sous-menu / valeur suivante |
| `←` ou `ESC` | Retour / valeur précédente |
| `Entrée` sur champ texte | Activer saisie |

---

## Police personnalisable

Dans `config.yaml` :
```yaml
app:
  font_path: assets/fonts/Montserrat-Regular.ttf
```

Télécharger gratuitement sur [fonts.google.com](https://fonts.google.com) (format TTF), copier dans `assets/fonts/`. La même police s'applique à l'interface ET aux textes sur les photos finales.

---

## Templates 10×15 cm

| Template              | Dimensions  | Orientation | Photos |
|-----------------------|-------------|-------------|--------|
| `portrait_1photo`     | 1181×1772 px | Portrait    | 1      |
| `landscape_4photos`   | 1772×1181 px | Paysage     | 4      |

Chaque template supporte un **titre** et une **description** configurables depuis le menu admin.  
Voir [docs/TEMPLATES.md](docs/TEMPLATES.md) pour créer ses propres templates.

---

## IA — Remplacement de fond

| Provider       | Qualité  | Vitesse Pi 4 | Internet | Coût    |
|----------------|----------|:------------:|:--------:|---------|
| `rembg`        | ⭐⭐⭐⭐  | ~4-8 s       | Non      | Gratuit |
| `mediapipe`    | ⭐⭐⭐    | <1 s         | Non      | Gratuit |
| `removebg_api` | ⭐⭐⭐⭐⭐ | ~2 s         | Oui      | 50/mois gratuit |

**Recommandé : `rembg`** — qualité/autonomie optimale pour photobooth.

---

## Documentation

- [Installation complète](docs/INSTALLATION.md)
- [Câblage GPIO](docs/GPIO_WIRING.md)
- [Créer un template](docs/TEMPLATES.md)
- [Procédures de test](docs/TESTING.md)
- [Git & déploiement Raspberry Pi](docs/Create_Update_Git_Raspberry.md)
