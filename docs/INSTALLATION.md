# Installation — SnapForge PhotoBooth Raspberry Pi

## Matériel requis

- Raspberry Pi 4 (4 Go recommandés) ou Pi 5
- Carte microSD ≥ 32 Go (Classe 10 / A1)
- Alimentation officielle Pi 4 (USB-C, 5V/3A)
- Écran HDMI (800×480 minimum recommandé)
- Caméra Raspberry Pi v2 (IMX219)
- 2 boutons poussoirs NO (normalement ouvert)
- 5 LEDs + résistances 220 Ω
- Câbles Dupont femelle-femelle

---

## 1. Système

Flasher **Raspberry Pi OS Trixie 64-bit (Desktop)** avec Raspberry Pi Imager.

> Activer SSH, configurer Wi-Fi et nom d'hôte `snapforge` directement dans l'Imager (icône engrenage).

```bash
sudo apt update && sudo apt upgrade -y

# Activer la caméra
sudo raspi-config
# → Interface Options → Camera → Enable

# Dépendances système
sudo apt install -y \
    python3-picamera2 python3-libcamera \
    python3-pygame python3-pil \
    cups cups-client \
    git

# Pour Pi 5 (backend lgpio)
# sudo apt install -y python3-lgpio
```

---

## 2. Clonage et environnement

```bash
cd /home/guillaume
git clone https://github.com/gdrau/SnapForge.git
cd SnapForge

# --system-site-packages est obligatoire pour accéder à picamera2 (installé via apt)
python3 -m venv venv --system-site-packages
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Configuration

```bash
cp config.example.yaml config.yaml
nano config.yaml
```

**Paramètres minimaux à vérifier :**

```yaml
app:
  booth_name: "Mon PhotoBooth"    # Nom affiché sur l'écran d'accueil
  fullscreen: true
  font_path: assets/fonts/Montserrat-Regular.ttf  # Optionnel (voir section Police)

event:
  title: "Mon Événement"
  description: "14 juin 2026"

photos:
  option_a: 1                     # Première option proposée à l'utilisateur
  option_b: 4                     # Deuxième option

camera:
  flip_horizontal: false          # Mettre true si image miroir
  flip_vertical: false

session:
  countdown_seconds: 3

qr:
  base_url: "http://VOTRE-IP/photos"   # URL pour les QR codes

templates:
  photo_1: portrait_1photo        # Template utilisé pour 1 photo
  photo_4: landscape_4photos      # Template utilisé pour 4 photos
```

---

## 4. Police personnalisée (optionnel)

Télécharger une police TTF sur [fonts.google.com](https://fonts.google.com) (ex: Montserrat, Raleway, Playfair Display).

```bash
# Copier la police dans le projet
cp ~/Téléchargements/Montserrat-Regular.ttf assets/fonts/

# Puis dans config.yaml :
# app:
#   font_path: assets/fonts/Montserrat-Regular.ttf
```

---

## 5. Tests initiaux

```bash
source venv/bin/activate

# Tester GPIO (boutons + LEDs)
python scripts/test_gpio.py

# Tester la caméra
python scripts/test_camera.py

# Lancer en mode fenêtré (test sans plein écran)
python src/app.py --windowed
```

---

## 6. Service systemd (démarrage automatique au boot)

Le fichier `snapforge.service` est inclus dans le dépôt :

```ini
[Unit]
Description=SnapForge PhotoBooth
After=network.target graphical.target

[Service]
Type=simple
User=guillaume
Group=guillaume
WorkingDirectory=/home/guillaume/SnapForge
ExecStart=/home/guillaume/SnapForge/venv/bin/python src/app.py --config config.yaml

Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/guillaume/.Xauthority
Environment=SDL_VIDEODRIVER=x11
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8

Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=snapforge

[Install]
WantedBy=graphical.target
```

> Adapter `User`, `Group` et les chemins si votre utilisateur n'est pas `guillaume`.

```bash
# Installer et activer
sudo cp /home/guillaume/SnapForge/snapforge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable snapforge
sudo systemctl start snapforge

# Vérifier
sudo systemctl status snapforge
journalctl -u snapforge -f
```

---

## 7. Réseau — servir les photos via HTTP (QR codes)

```bash
sudo apt install nginx

sudo nano /etc/nginx/sites-available/snapforge
```

```nginx
server {
    listen 80;
    server_name _;
    location /photos {
        alias /home/guillaume/SnapForge/Photo/final;
        autoindex on;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/snapforge /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

Dans `config.yaml`, mettre l'adresse IP ou le hostname du Pi :
```yaml
qr:
  base_url: "http://192.168.1.X/photos"
```

---

## 8. IA rembg (optionnel)

```bash
source venv/bin/activate
pip install rembg onnxruntime

# Le modèle (~170 Mo) est téléchargé au premier lancement
python -c "from rembg import new_session; new_session('u2net'); print('rembg OK')"
```

Dans `config.yaml` :
```yaml
ai:
  enabled: true
  provider: rembg
  background_path: assets/backgrounds/default_bg.jpg
```

> Le remplacement de fond se fait en arrière-plan après la capture, pas en temps réel.

---

## 9. Imprimante CUPS (optionnel)

```bash
sudo usermod -a -G lpadmin guillaume
sudo systemctl enable cups && sudo systemctl start cups
# Interface web CUPS : http://IP:631
```

Dans `config.yaml` :
```yaml
printing:
  enabled: true
  printer_name: "Canon_SELPHY_CP1300"  # Nom exact de l'imprimante CUPS
```

---

## 10. Export USB — désactiver l'automount graphique

Par défaut, Raspberry Pi OS affiche une notification ou ouvre le gestionnaire de fichiers à chaque insertion de clé USB, ce qui sort l'utilisateur de SnapForge. Voici comment le désactiver selon votre version.

### Étape 1 — Identifier votre environnement de bureau

```bash
echo $DESKTOP_SESSION
# ou
ps aux | grep -E "lxsession|lxqt|wayfire|openbox" | grep -v grep | head -3
```

---

### Raspberry Pi OS (LXDE / PCManFM) — le plus courant

```bash
# Trouver le profil actif
ls ~/.config/pcmanfm/

# Appliquer sur le profil LXDE-pi (standard Raspberry Pi OS)
mkdir -p ~/.config/pcmanfm/LXDE-pi
cat > ~/.config/pcmanfm/LXDE-pi/pcmanfm.conf << 'EOF'
[volume]
mount_on_startup=0
mount_removable=0
autorun=0
EOF

# Si votre profil s'appelle "LXDE" (pas "LXDE-pi"), adaptez :
mkdir -p ~/.config/pcmanfm/LXDE
cp ~/.config/pcmanfm/LXDE-pi/pcmanfm.conf ~/.config/pcmanfm/LXDE/pcmanfm.conf
```

Puis redémarrez PCManFM :

```bash
pkill pcmanfm; sleep 1
pcmanfm --desktop &
```

---

### Raspberry Pi OS Bookworm/Trixie (GNOME ou Wayfire)

```bash
gsettings set org.gnome.desktop.media-handling automount false
gsettings set org.gnome.desktop.media-handling automount-open false
gsettings set org.gnome.desktop.media-handling autorun-never true
```

---

### Solution universelle — désactiver via autostart (toutes versions)

Crée un script au démarrage de session qui désactive l'automount :

```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/disable-automount.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=Disable USB Automount
Exec=bash -c "gsettings set org.gnome.desktop.media-handling automount false 2>/dev/null; gsettings set org.gnome.desktop.media-handling automount-open false 2>/dev/null"
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
```

---

### Vérification

Après redémarrage, branchez une clé USB : aucune fenêtre ne doit apparaître.

> **Important :** le montage automatique (udisks2) reste actif — c'est ce dont SnapForge a besoin pour détecter la clé. Seule l'ouverture graphique est désactivée.

---

## 11. Mise à jour

```bash
cd /home/guillaume/SnapForge
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart snapforge
```

Ou utiliser le script inclus :
```bash
./update.sh
```
