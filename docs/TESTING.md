# Procédures de test — PhotoBooth

## Prérequis communs

```bash
cd /home/pi/photobooth
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
- En appuyant sur chaque bouton dans les 10s : `✓ BTN photo pressé` / `✓ BTN print pressé`

**Dépannage :**
- `ERREUR : gpiozero non disponible` → `pip install gpiozero`
- LED ne s'allume pas → vérifier résistance et sens d'insertion de la LED
- Bouton non détecté → vérifier câblage entre pin GPIO et GND

---

## 2. Test caméra

```bash
python scripts/test_camera.py
```

**Résultat attendu :**
```
1. Démarrage preview 5s…
   Frames reçues : 150 (30.0 fps)
2. Capture photo…
   Sauvegardé : photos/test_capture.jpg (2840 Ko)
   Dimensions : 3280×2464 px
   Capture OK ✓
```

**Dépannage :**
- `Picamera2 indisponible` → `sudo apt install python3-picamera2`
- Erreur d'initialisation → vérifier le câble nappe de la caméra et activer dans `raspi-config`

---

## 3. Test QR code

```bash
python scripts/test_qr.py
```

**Résultat attendu :**
```
QR code généré : photos/test_qrcode.png
Dimensions : (300, 300)
URL encodée : http://photobooth.local/photos/photobooth_20260101_120000.jpg
Test OK ✓
```

Pour vérifier le QR code : ouvrir `photos/test_qrcode.png` et le scanner avec un smartphone.

**Dépannage :**
- `qrcode non installé` → `pip install qrcode[pil]`

---

## 4. Test IA (rembg)

```bash
# D'abord avoir une photo de test :
python scripts/test_camera.py
# Puis tester l'IA :
python scripts/test_ai.py
```

**Résultat attendu :**
```
Provider : rembg
Traitement de : photos/test_capture.jpg
Résultat : photos/test_ai_result.jpg (1450 Ko)
Durée    : 4.2s
Test OK ✓
```

**Dépannage :**
- `rembg non installé` → `pip install rembg onnxruntime`
- Premier lancement lent (~30s) : téléchargement du modèle U2Net (~170 Mo)
- Erreur mémoire : activer le swap sur Pi 4 (`sudo dphys-swapfile swapoff && sudo nano /etc/dphys-swapfile` → CONF_SWAPSIZE=1024)

---

## 5. Test application complète (mode fenêtré)

```bash
python src/app.py --windowed
```

**Workflow de test :**
1. Écran d'accueil affiché → OK
2. Appui `ESPACE` ou bouton photo → écran choix format → OK
3. Clic sur format ou bouton print → cycle de formats → OK
4. Clic `DÉMARRER` → preview caméra → OK
5. Clic `CAPTURER` ou bouton photo → compte à rebours → capture → OK
6. Répéter pour chaque photo du format
7. Processing → image finale affichée → OK
8. Clic `CONTINUER` → (upload) → QR code affiché → OK
9. QR code disparaît après 15s → retour accueil → OK
10. Touche `ÉCHAP` depuis n'importe quel écran → retour accueil → OK

---

## 6. Test service systemd

```bash
# Installation
sudo cp photobooth.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable photobooth
sudo systemctl start photobooth

# Vérification
sudo systemctl status photobooth
journalctl -u photobooth -f

# Arrêt / redémarrage
sudo systemctl stop photobooth
sudo systemctl restart photobooth
```
