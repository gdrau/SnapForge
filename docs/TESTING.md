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

**Workflow photo :**

| Étape | Action | Résultat attendu |
|-------|--------|-----------------|
| 1 | Écran d'accueil | Nom du photobooth + 2 lignes de titre + "Bienvenue !" + carrousel |
| 2 | Cliquer "APPUYEZ POUR COMMENCER" | Écran choix Photo / GIF |
| 3 | Cliquer "PHOTO" | Écran choix du nombre de photos |
| 4 | Cliquer "1 PHOTO" | Preview caméra |
| 5 | Attendre 10s sans rien faire | Retour automatique à l'accueil |
| 6 | Relancer, cliquer "CAPTURER" | Compte à rebours 3-2-1 |
| 7 | Après capture | Traitement + assemblage template 400 DPI |
| 8 | Écran résultat | Photo finale + QR code |
| 9 | Cliquer "RETOUR ACCUEIL" | Retour à l'accueil |

**Workflow GIF :**

| Étape | Action | Résultat attendu |
|-------|--------|-----------------|
| 1 | Accueil → "GIF ANIMÉ" | Écran choix d'orientation |
| 2 | Cliquer "PORTRAIT" ou "PAYSAGE" | Preview caméra |
| 3 | Cliquer "CAPTURER" | N captures automatiques avec délai |
| 4 | Génération | Écran "Traitement GIF..." |
| 5 | Résultat | QR code + aperçu GIF animé |
| 6 | Accueil | GIF visible dans le carrousel (miniature animée) |

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
- Entrer dans **Configuration** → modifier les deux lignes de nom + taille police
- Entrer dans **Export USB** → activer / désactiver le bouton USB
- Sauvegarder → vérifier que `config.yaml` est mis à jour

**Dialogues de confirmation à tester :**
- **Quitter l'application** → dialogue avec boutons "Annuler" (gauche) et "Confirmer" (droite) : BTN1 GPIO = Annuler, BTN2 GPIO = Confirmer
- **Remise à zéro** → même comportement : BTN1 GPIO = Annuler, BTN2 GPIO = Confirmer
- Après reset : les anciennes photos doivent disparaître immédiatement du carrousel (cache mémoire vidé)

---

## 6b. Test inactivité

```bash
python src/app.py --windowed
```

- Aller sur l'écran "Choix Photo / GIF"
- Ne rien faire pendant 10 secondes
- Résultat attendu : retour automatique à l'accueil

Le timer se remet à zéro à chaque clic ou touche clavier.
L'admin et l'écran QR code ne sont **pas** affectés par l'inactivité.

---

## 6c. Test export USB (sur Raspberry Pi uniquement)

1. Activer l'export dans Admin → Export USB → "Export USB activé" → ACTIVE → Sauvegarder
2. Brancher une clé USB (auto-montage sous `/media/pi/`)
3. Depuis l'écran d'accueil, appuyer sur **BTN 3 (PIN 16)**
4. L'écran "Export USB" s'affiche avec les étapes de copie
5. Après quelques secondes : "Export terminé — X fichiers copiés"
6. Retour automatique à l'accueil après 3s
7. Vérifier sur la clé : `Photos_PhotoBooth/Photos_Template/`, `Photos_Originales/`, `GIF_Animes/`

**Sans clé USB :** "Aucune clé USB détectée" → retour automatique après 3s.
**Hors écran d'accueil :** le bouton est ignoré.

---

## 7. Test polices personnalisées

```bash
# Copier des polices TTF (ex: depuis Google Fonts)
cp ~/Téléchargements/Roboto-Regular.ttf assets/fonts/
cp ~/Téléchargements/AmaticSC-Bold.ttf assets/fonts/
```

**Tester `app.font_path` (interface) :**

Dans `config.yaml` :
```yaml
app:
  font_path: assets/fonts/Roboto-Regular.ttf
```

Relancer l'app → la police doit être visible sur l'écran d'accueil, les menus et les boutons.

**Tester `processing.font_path` (textes sur photo finale) :**

Dans `config.yaml` :
```yaml
processing:
  font_path: assets/fonts/AmaticSC-Bold.ttf
```

Relancer l'app, prendre une photo → le titre et la description sur l'image finale doivent utiliser AmaticSC-Bold.

**Tester le fallback :** supprimer `processing.font_path` → les textes sur la photo finale doivent utiliser `app.font_path`.

---

## 7b. Test qualité photo (résolution max)

```bash
python scripts/test_quality_photo.py
```

**Résultat attendu :**
```
Résolution maximale : 3280 x 2464 px
Capture 1/3  qualité=95  taille=~4200 Ko  netteté=XXX  durée=X.Xs
Capture 2/3  qualité=85  taille=~3100 Ko  netteté=XXX  durée=X.Xs
Capture 3/3  qualité=70  taille=~2000 Ko  netteté=XXX  durée=X.Xs
```

Le score de netteté est calculé via la variance du Laplacien — plus il est élevé, plus la mise au point est précise. Les fichiers sont sauvegardés dans `Photo/test_quality/`.

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
│   └── 20260606_143022/                       ← une session photo
│       ├── photo_0001_01_20260606_143022.jpg   ← brutes horodatées
│       └── photo_0001_02_20260606_143022.jpg
├── final/
│   └── snapforge_0001_20260606_143022.jpg     ← image finale (template 400 DPI)
├── gifs/
│   └── gif_0001_20260606_143022.gif           ← GIF animés générés
├── thumbnails/
│   └── gif_0001_20260606_143022.jpg           ← miniature du GIF pour carrousel
├── exported/                                  ← copie locale si upload cloud activé
└── tests/                                     ← photos des scripts de test
    ├── test_capture.jpg
    ├── test_qrcode.png
    └── test_ai_result.jpg
```

**Structure export USB (clé USB) :**

```
Photos_PhotoBooth/          (ou Photos_PhotoBooth_1, _2… si export précédent)
├── Photos_Template/        ← images finales avec template, titre, QR code
├── Photos_Originales/      ← photos brutes sans traitement
└── GIF_Animes/             ← GIF animés
```
