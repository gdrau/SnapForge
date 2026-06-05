# Créer, pousser et mettre à jour le projet SnapForge

---

## 1. Créer le dépôt GitHub et pousser le projet (première fois)

### Étape 1 — Créer le dépôt sur GitHub

1. Connectez-vous sur [github.com](https://github.com)
2. Cliquez sur **"New repository"** (bouton vert en haut à droite)
3. Remplissez :
   - **Repository name** : `photobooth` (ou le nom de votre choix)
   - **Description** : `SnapForge Raspberry Pi — Picamera2 + Pygame`
   - **Visibility** : Public ou Private selon votre préférence
   - ⚠️ **Ne cochez rien** dans "Initialize this repository" (pas de README, pas de .gitignore)
4. Cliquez sur **"Create repository"**
5. GitHub affiche une page avec une URL du type :
   ```
   https://github.com/gdrau/SnapForge.git
   ```
   Copiez cette URL, vous en aurez besoin à l'étape 3.

---

### Étape 2 — Configurer votre identité Git (si pas encore fait)

Ouvrez un terminal dans `c:\projets\SnapForge` :

```bash
git config --global user.name "Votre Nom"
git config --global user.email "votre@email.com"
```

---

### Étape 3 — Lier votre dépôt local à GitHub et pousser

```bash
# Depuis c:\projets\SnapForge
git remote add origin https://github.com/gdrau/SnapForge.git
git branch -M main
git push -u origin main
```

> Si GitHub vous demande un mot de passe, utilisez un **Personal Access Token** (pas votre mot de passe).
> Générez-en un sur : GitHub → Settings → Developer settings → Personal access tokens → Generate new token (cochez `repo`).

---

### Étape 4 — Vérifier que tout est en ligne

Rendez-vous sur `https://github.com/gdrau/SnapForge` — vous devez voir tous vos fichiers et le README s'afficher.

---

## 2. Mettre à jour le dépôt GitHub après une modification

Chaque fois que vous modifiez des fichiers sur votre PC, suivez cette procédure :

```bash
# Depuis c:\projets\SnapForge

# 1. Voir ce qui a changé
git status

# 2. Ajouter les fichiers modifiés
#    (option a) tout ajouter sauf ce qui est dans .gitignore :
git add .

#    (option b) ajouter fichier par fichier si vous voulez être précis :
git add src/ui/pygame_ui.py
git add src/state_machine.py

# 3. Créer un commit avec un message clair
git commit -m "Description courte de ce que vous avez changé"

# 4. Pousser vers GitHub
git push
```

### Exemples de messages de commit

```bash
git commit -m "Correction taille boutons écran format"
git commit -m "Ajout template portrait duo"
git commit -m "Amélioration menu admin : ajout option template"
git commit -m "Fix encodage UTF-8 logs Windows"
```

> **Bonne pratique** : faites un commit par modification logique, pas un seul gros commit pour tout.

---

## 3. Installer le projet sur le Raspberry Pi (première fois)

### Prérequis système

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y \
    python3-picamera2 python3-libcamera \
    python3-pygame python3-pil \
    git curl
```

### Installation

```bash
cd /home/pi

# Cloner le projet depuis GitHub
git clone https://github.com/gdrau/SnapForge.git
cd SnapForge

# Créer la configuration locale
cp config.example.yaml config.yaml
nano config.yaml
# → Adaptez les paramètres à votre matériel (résolution, GPIO, etc.)

# Créer l'environnement Python
# --system-site-packages donne accès à picamera2 installé via apt
python3 -m venv venv --system-site-packages
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Vérifier que tout fonctionne
python scripts/test_camera.py
python scripts/test_gpio.py

# Lancer le photobooth
python src/app.py
```

### Installer le service systemd (démarrage automatique au boot)

```bash
# Vérifier le chemin dans le fichier service
nano /home/pi/SnapForge/snapforge.service
# → WorkingDirectory et ExecStart doivent pointer vers /home/pi/SnapForge

# Installer et activer le service
sudo cp /home/pi/SnapForge/snapforge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable photobooth
sudo systemctl start photobooth

# Vérifier que le service tourne
sudo systemctl status photobooth
```

---

## 4. Mettre à jour le Raspberry Pi après une modification

Quand vous avez poussé des modifications sur GitHub depuis votre PC, mettez à jour le Raspberry Pi :

```bash
# Connexion SSH au Raspberry Pi depuis votre PC
ssh pi@ADRESSE_IP_DU_PI

# Se placer dans le projet
cd /home/pi/SnapForge

# Arrêter le service si actif
sudo systemctl stop photobooth

# Récupérer les dernières modifications depuis GitHub
git pull

# Si vous avez ajouté des dépendances Python
source venv/bin/activate
pip install -r requirements.txt

# Redémarrer le service
sudo systemctl start photobooth

# Vérifier
sudo systemctl status photobooth
journalctl -u photobooth -n 30
```

### Script de mise à jour rapide (optionnel)

Créez un fichier `/home/pi/SnapForge/update.sh` :

```bash
#!/bin/bash
set -e
cd /home/pi/SnapForge
echo "Arrêt du service..."
sudo systemctl stop photobooth
echo "Récupération des mises à jour..."
git pull
echo "Mise à jour des dépendances..."
source venv/bin/activate
pip install -r requirements.txt --quiet
echo "Redémarrage..."
sudo systemctl start photobooth
echo "Mise à jour terminée."
sudo systemctl status photobooth --no-pager
```

Rendez-le exécutable :

```bash
chmod +x /home/pi/SnapForge/update.sh
```

Utilisation :

```bash
cd /home/pi/SnapForge
./update.sh
```

---

## Résumé des commandes essentielles

| Action | Commande |
|--------|----------|
| Voir les fichiers modifiés | `git status` |
| Ajouter tous les changements | `git add .` |
| Créer un commit | `git commit -m "message"` |
| Pousser sur GitHub | `git push` |
| Récupérer depuis GitHub (Pi) | `git pull` |
| Historique des commits | `git log --oneline` |
| Annuler les modifs non commitées | `git restore .` |
| Voir les différences | `git diff` |
