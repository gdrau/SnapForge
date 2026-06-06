# Créer, pousser et mettre à jour SnapForge

---

## 1. Créer le dépôt GitHub et pousser le projet (première fois)

### Étape 1 — Créer le dépôt sur GitHub

1. Connectez-vous sur [github.com](https://github.com)
2. Cliquez **"New repository"**
3. Paramètres :
   - **Repository name** : `SnapForge`
   - **Visibility** : Public ou Private
   - ⚠️ **Ne cochez rien** (pas de README, pas de .gitignore à l'init)
4. Cliquez **"Create repository"**
5. Copiez l'URL : `https://github.com/gdrau/SnapForge.git`

### Étape 2 — Configurer votre identité Git (si pas encore fait)

```bash
git config --global user.name "Votre Nom"
git config --global user.email "votre@email.com"
```

### Étape 3 — Pousser vers GitHub

```bash
# Depuis c:\projets\PhotoBooth (Windows)
git remote add origin https://github.com/gdrau/SnapForge.git
git branch -M main
git push -u origin main
```

> Si GitHub demande une authentification, utilisez un **Personal Access Token** (pas votre mot de passe).  
> Générer : GitHub → Settings → Developer settings → Personal access tokens → Generate new token (cocher `repo`).

---

## 2. Mettre à jour le dépôt GitHub après une modification

```bash
# Voir ce qui a changé
git status

# Ajouter les fichiers modifiés
git add .
# OU fichier par fichier :
git add src/ui/pygame_ui.py templates/portrait_1photo.json

# Créer un commit
git commit -m "Description des modifications"

# Pousser vers GitHub
git push
```

### Exemples de messages de commit

```bash
git commit -m "Ajout police Montserrat"
git commit -m "Correction navigation menu admin"
git commit -m "Nouveau template duo portrait 2 photos"
git commit -m "Fix timeout camera au demarrage"
```

---

## 3. Installer le projet sur le Raspberry Pi (première fois)

### Prérequis système

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y \
    python3-picamera2 python3-libcamera \
    python3-pygame python3-pil \
    git
```

### Installation

```bash
cd /home/guillaume

# Cloner depuis GitHub
git clone https://github.com/gdrau/SnapForge.git
cd SnapForge

# Configuration
cp config.example.yaml config.yaml
nano config.yaml
# → Adapter : booth_name, base_url QR, option_a/option_b, etc.

# Environnement Python
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install -r requirements.txt

# Tests
python scripts/test_camera.py
python scripts/test_gpio.py

# Lancer
python src/app.py
```

### Installer le service systemd (démarrage automatique au boot)

Le fichier `snapforge.service` est inclus dans le dépôt avec le contenu suivant :

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

> Si vous avez cloné ailleurs que `/home/guillaume/SnapForge`, adaptez `User`, `Group`, `WorkingDirectory` et `ExecStart` :
> ```bash
> nano /home/guillaume/SnapForge/snapforge.service
> ```

```bash
# Installer et activer
sudo cp /home/guillaume/SnapForge/snapforge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable snapforge
sudo systemctl start snapforge

# Vérifier
sudo systemctl status snapforge

# Logs en direct
journalctl -u snapforge -f
```

---

## 4. Mettre à jour le Raspberry Pi après une modification

Après avoir poussé des changements depuis votre PC :

```bash
# Connexion SSH
ssh guillaume@ADRESSE_IP_DU_PI

cd /home/guillaume/SnapForge

# Arrêter le service
sudo systemctl stop snapforge

# Récupérer les mises à jour
git pull

# Si des dépendances ont changé
source venv/bin/activate
pip install -r requirements.txt

# Redémarrer
sudo systemctl start snapforge

# Vérifier
sudo systemctl status snapforge
journalctl -u snapforge -n 30
```

### Script de mise à jour rapide

Créez `update.sh` à la racine du projet (déjà inclus) :

```bash
#!/bin/bash
set -e
cd /home/guillaume/SnapForge
echo "Arrêt du service..."
sudo systemctl stop snapforge
echo "Mise à jour depuis GitHub..."
git pull
echo "Mise à jour des dépendances..."
source venv/bin/activate
pip install -r requirements.txt --quiet
echo "Redémarrage..."
sudo systemctl start snapforge
echo "Terminé."
sudo systemctl status snapforge --no-pager
```

```bash
chmod +x update.sh
./update.sh
```

---

## 5. Dépannage git courant

### Dépôt corrompu (object file empty)

```bash
cd /home/guillaume

# Sauvegarder config.yaml (gitignored)
cp SnapForge/config.yaml /tmp/config_backup.yaml

# Supprimer et recloner
rm -rf SnapForge
git clone https://github.com/gdrau/SnapForge.git
cd SnapForge

# Restaurer la config
cp /tmp/config_backup.yaml config.yaml

# Recréer le venv
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install -r requirements.txt
```

### Fichier local bloquant le pull

```bash
git status                          # Voir les fichiers modifiés localement
git diff src/camera/picamera2_camera.py  # Voir les différences
git checkout src/camera/picamera2_camera.py  # Annuler les modifications locales
git pull
```

### Vider le cache Python (ImportError inattendu)

```bash
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
```

---

## 6. Résumé des commandes essentielles

| Action | Commande |
|--------|----------|
| Voir les fichiers modifiés | `git status` |
| Ajouter tous les changements | `git add .` |
| Créer un commit | `git commit -m "message"` |
| Pousser sur GitHub | `git push` |
| Récupérer depuis GitHub (Pi) | `git pull` |
| Historique des commits | `git log --oneline -10` |
| Annuler modifs non commitées | `git restore .` |
| Voir les différences | `git diff` |
| Logs service | `journalctl -u snapforge -f` |
| Redémarrer service | `sudo systemctl restart snapforge` |
