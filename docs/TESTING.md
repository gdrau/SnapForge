# Procédures de test — SnapForge

## Prérequis

```bash
cd /home/guillaume/SnapForge
source venv/bin/activate
```

---

## 1. Test boutons et LEDs GPIO

```bash
python scripts/test_gpio.py
```

**Résultat attendu :**
- Chaque LED s'allume 1 seconde puis s'éteint
- Toutes les LEDs clignotent 3 secondes
- Appuyer sur chaque bouton dans les 10s → `✓ BTN photo pressé` / `✓ BTN print pressé`

**Dépannage :**
- `gpiozero indisponible` → normal si test sur PC
- LED ne s'allume pas → vérifier résistance 220Ω et sens de la LED
- Bouton non détecté → vérifier câblage entre pin GPIO et GND

---

## 2. Test caméra

```bash
python scripts/test_camera.py
```

**Résultat attendu :**
```
SnapForge — Test Caméra

1. Démarrage preview 5s...
   Frames reçues : 167 (33.4 fps)
   Preview OK ✓

2. Capture photo...
   Fichier    : /home/guillaume/SnapForge/Photo/tests/test_capture.jpg
   Taille     : ~2800 Ko
   Dimensions : 3280 x 2464 px
   Capture OK ✓
```

**Si timeout caméra** (`Camera frontend has timed out`) :
```bash
# Tester hors de l'application
libcamera-hello --timeout 5000
```
Si erreur également → vérifier le câble nappe CSI (réencastrer les deux extrémités).

---

## 3. Test QR code

```bash
python scripts/test_qr.py
```

**Résultat attendu :**
```
QR code généré : /home/guillaume/SnapForge/Photo/tests/test_qrcode.png
Dimensions     : (300, 300)
URL encodée    : http://snapforge.local/photos/snapforge_20260101_120000.jpg
Test OK ✓
```

Scanner le QR code avec un smartphone pour vérifier l'URL encodée.

**Dépannage :**
- `qrcode non installé` → `pip install qrcode[pil]`

---

## 4. Test IA (rembg)

```bash
# Avoir d'abord une photo de test
python scripts/test_camera.py

# Puis tester l'IA
python scripts/test_ai.py
```

**Résultat attendu :**
```
Provider : rembg
Traitement de  : /home/guillaume/SnapForge/Photo/tests/test_capture.jpg
Résultat       : /home/guillaume/SnapForge/Photo/tests/test_ai_result.jpg
Taille         : 1450 Ko
Durée          : 4.2s
Test OK ✓
```

**Dépannage :**
- `rembg non installé` → `pip install rembg onnxruntime`
- Premier lancement lent (~30s) : téléchargement du modèle U2Net (~170 Mo)
- Erreur mémoire → augmenter le swap : `sudo dphys-swapfile swapoff && sudo nano /etc/dphys-swapfile` → `CONF_SWAPSIZE=1024`

---

## 5. Test application complète (mode fenêtré)

```bash
python src/app.py --windowed
```

**Workflow de test :**

| Étape | Action | Résultat attendu |
|-------|--------|-----------------|
| 1 | Écran d'accueil | Nom du photobooth + bouton orange |
| 2 | Cliquer "APPUYEZ POUR COMMENCER" | Écran choix format |
| 3 | Cliquer "1 PHOTO" | Preview caméra |
| 4 | Cliquer "CAPTURER" | Compte à rebours 3-2-1 |
| 5 | Après capture | Traitement + assemblage |
| 6 | Écran résultat | Photo finale + QR code |
| 7 | Cliquer "RETOUR ACCUEIL" | Retour à l'accueil |
| 8 | Touche `ESC` | Menu administration |
| 9 | Naviguer dans les sous-menus | Admin fonctionnel |
| 10 | Modifier le nom dans Config | Sauvegarde dans config.yaml |

---

## 6. Test menu administration

```bash
python src/app.py --windowed
# Puis appuyer sur ESC
```

**Navigation à tester :**
- `↓`/`↑` : naviguer sans dépasser les limites (pas d'item fantôme)
- `→` ou `Entrée` : ouvrir un sous-menu
- `←` ou `ESC` : retour sans perdre la position dans le menu parent
- Entrer dans **Configuration** : modifier le nom du photobooth au clavier
- Sauvegarder → vérifier que `config.yaml` est mis à jour

---

## 7. Test police personnalisée

```bash
# Copier une police TTF (ex: Montserrat depuis Google Fonts)
cp ~/Téléchargements/Montserrat-Regular.ttf assets/fonts/
```

Dans `config.yaml` :
```yaml
app:
  font_path: assets/fonts/Montserrat-Regular.ttf
```

Relancer l'app → la police doit être visible sur l'écran d'accueil et sur les photos finales.

---

## 8. Test service systemd

```bash
# Installation
sudo cp snapforge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable snapforge
sudo systemctl start snapforge

# Vérification
sudo systemctl status snapforge
journalctl -u snapforge -f

# Arrêt / redémarrage
sudo systemctl stop snapforge
sudo systemctl restart snapforge
```

**Logs attendus au démarrage :**
```
INFO  gpio.buttons: Bouton BOARD11 initialise (bounce=0.05s)
INFO  gpio.lights:  LED initialisée sur pin BOARD 7
INFO  processing.composer: Template charge : portrait_1photo (...)
INFO  processing.composer: Templates disponibles : [...]
INFO  camera.picamera2_camera: Picamera2 initialisee et operationnelle (800x480px)
INFO  ui.pygame_ui: Pygame UI : 800x480 fullscreen=True
INFO  state_machine: [FSM] IDLE -> IDLE
```

---

## Structure des photos générées

```
Photo/
├── raw/
│   └── 20260606_143022/                    ← une session
│       ├── photo_0001_01_20260606_143022.jpg  ← brutes horodatées
│       ├── photo_0001_02_20260606_143022.jpg
│       └── qrcode.png
├── final/
│   └── snapforge_0001_20260606_143022.jpg  ← image finale
├── exported/                               ← copie locale si upload activé
└── tests/                                  ← photos des scripts de test
    ├── test_capture.jpg
    ├── test_qrcode.png
    └── test_ai_result.jpg
```
