# Installation — PhotoBooth Raspberry Pi

## Matériel requis

- Raspberry Pi 4 (4 Go recommandés)
- Carte microSD ≥ 32 Go (Classe 10 / A1)
- Alimentation officielle Pi 4 (USB-C, 5V/3A)
- Écran HDMI (800×480 minimum recommandé)
- Caméra Raspberry Pi v2 (IMX219)
- 2 boutons poussoirs NO (normalement ouvert)
- 5 LEDs + résistances 220 Ω
- Câbles Dupont femelle-femelle

## 1. Système

Flasher **Raspberry Pi OS Bookworm 64-bit** avec Raspberry Pi Imager.

Activer SSH et configurer Wi-Fi dans Imager si besoin.

```bash
sudo apt update && sudo apt upgrade -y

# Activer la caméra
sudo raspi-config
# → Interface Options → Camera → Enable

# Dépendances système
sudo apt install -y \
    python3-picamera2 python3-libcamera \
    python3-pygame python3-pil \
    libopencv-dev python3-opencv \
    cups cups-client \
    git

# Pour gpiozero sur Pi 5 (lgpio backend)
# sudo apt install -y python3-lgpio
```

## 2. Clonage et environnement

```bash
cd /home/pi
git clone https://github.com/gdrau/SnapForge.git
cd SnapForge

python3 -m venv venv --system-site-packages
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

> `--system-site-packages` est nécessaire pour que picamera2 (installé via apt) soit accessible dans le venv.

## 3. Configuration

```bash
cp config.example.yaml config.yaml
nano config.yaml
```

Paramètres minimaux à ajuster :

```yaml
app:
  fullscreen: true    # false pour développement

camera:
  flip_horizontal: false   # Ajuster si image miroir

qr:
  base_url: "http://VOTRE-IP-OU-HOSTNAME/photos"
```

## 4. Test initial

```bash
source venv/bin/activate

# Tester le GPIO
python scripts/test_gpio.py

# Tester la caméra
python scripts/test_camera.py

# Lancer en mode fenêtré
python src/app.py --windowed
```

## 5. Installation du service systemd

```bash
# Vérifier le chemin dans le service
nano snapforge.service
# Adapter WorkingDirectory et ExecStart si installé ailleurs que /home/pi/SnapForge

sudo cp snapforge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable photobooth
sudo systemctl start photobooth

# Vérifier
sudo systemctl status photobooth
journalctl -u photobooth -n 50
```

## 6. Démarrage automatique sur Pi sans bureau (optionnel)

Si vous utilisez le mode console (Lite) :

```bash
# Dans /boot/firmware/config.txt, ajouter :
dtoverlay=vc4-kms-v3d

# Créer un service X minimal ou utiliser directframebuffer SDL
# Modifier dans snapforge.service :
Environment=SDL_VIDEODRIVER=fbcon
Environment=SDL_FBDEV=/dev/fb0
```

## 7. Réseau — servir les photos via HTTP (pour les QR codes)

```bash
# Serveur web simple pour accéder aux photos depuis smartphone
sudo apt install nginx

sudo nano /etc/nginx/sites-available/photobooth
```

```nginx
server {
    listen 80;
    server_name _;
    location /photos {
        alias /home/pi/SnapForge/photos/final;
        autoindex on;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/photobooth /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

## 8. Installation IA rembg (optionnel)

```bash
source venv/bin/activate
pip install rembg onnxruntime

# Le modèle (~170 Mo) est téléchargé au premier lancement
python -c "from rembg import new_session; new_session('u2net'); print('rembg OK')"
```

Puis dans `config.yaml` :
```yaml
ai:
  enabled: true
  provider: rembg
  background_path: assets/backgrounds/default.jpg
```

## 9. Configuration imprimante CUPS (optionnel)

```bash
sudo usermod -a -G lpadmin pi
sudo systemctl enable cups
sudo systemctl start cups

# Interface web CUPS : http://IP:631
# Ajouter l'imprimante, noter son nom
```

Puis dans `config.yaml` :
```yaml
printing:
  enabled: true
  printer_name: "Canon_SELPHY_CP1300"  # Nom exact de l'imprimante CUPS
```

## Mise à jour

```bash
cd /home/pi/SnapForge
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart photobooth
```
