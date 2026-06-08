# Configuration Google Photos — SnapForge

Ce guide explique comment connecter SnapForge à votre compte Google Photos pour uploader automatiquement les photos après chaque session.

---

## Prérequis

- Un compte Google
- Accès à [console.cloud.google.com](https://console.cloud.google.com)
- Python installé sur votre PC (pour l'authentification initiale si le Pi n'a pas de navigateur)

```bash
# Installer les dépendances Google sur le Pi
source venv/bin/activate
pip install google-auth google-auth-oauthlib
```

---

## Étape 1 — Créer un projet Google Cloud

1. Aller sur [console.cloud.google.com](https://console.cloud.google.com)
2. Cliquer **"Nouveau projet"**
3. Nom du projet : `SnapForge`
4. Cliquer **"Créer"**

---

## Étape 2 — Activer l'API Photos Library

1. Menu gauche → **APIs et services** → **Bibliothèque**
2. Rechercher **"Photos Library API"**
3. Cliquer sur le résultat → **"Activer"**

---

## Étape 3 — Configurer l'écran de consentement OAuth

1. Menu gauche → **APIs et services** → **Écran de consentement OAuth**
2. Type d'utilisateur : **Externe** → **Créer**
3. Remplir les champs :
   - Nom de l'application : `SnapForge`
   - E-mail d'assistance utilisateur : votre adresse Gmail
   - Coordonnées du développeur : votre adresse Gmail
4. Cliquer **"Enregistrer et continuer"** (laisser les champs facultatifs vides)
5. Page "Utilisateurs test" → **"Ajouter des utilisateurs"** → entrer votre adresse Gmail
6. Cliquer **"Enregistrer et continuer"** puis **"Retour au tableau de bord"**

> **Important** : tant que l'application est en mode "Test", seuls les utilisateurs ajoutés à la liste peuvent autoriser l'accès. Cela est suffisant pour un usage personnel.

---

## Étape 4 — Créer les identifiants OAuth

1. Menu gauche → **APIs et services** → **Identifiants**
2. Cliquer **"Créer des identifiants"** → **"ID client OAuth"**
3. Type d'application : **Application de bureau**
4. Nom : `SnapForge`
5. Cliquer **"Créer"**
6. Dans la fenêtre qui s'affiche, cliquer **"Télécharger JSON"**
7. Renommer le fichier téléchargé en **`google_credentials.json`**

---

## Étape 5 — Copier les credentials sur le Raspberry Pi

```bash
# Depuis votre PC (remplacer ADRESSE_IP par l'IP de votre Pi)
scp google_credentials.json guillaume@ADRESSE_IP:/home/guillaume/SnapForge/credentials/

# Vérifier que le fichier est bien présent sur le Pi
ls /home/guillaume/SnapForge/credentials/
# Doit afficher : google_credentials.json
```

---

## Étape 6 — Configurer config.yaml

Ouvrir `/home/guillaume/SnapForge/config.yaml` et modifier les sections suivantes :

```yaml
cloud:
  enabled: true
  provider: google_photos
  retry_on_failure: true
  retry_queue_file: Photo/upload_queue.json

  google_photos:
    credentials_file: credentials/google_credentials.json
    album_name: "Mon Événement"     # nom de l'album créé automatiquement
```

Pour le QR code, vous pouvez pointer vers l'album ou garder le serveur local :

```yaml
qr:
  enabled: true
  base_url: "http://ADRESSE_IP_PI/photos"   # serveur local recommandé (voir note)
  display_duration: 15
```

---

## Étape 7 — Première authentification

La première connexion nécessite d'autoriser l'accès depuis un navigateur.

### Option A — Directement sur le Pi (si écran + souris connectés)

```bash
cd /home/guillaume/SnapForge
source venv/bin/activate
python src/app.py --windowed
```

Au premier upload, un lien s'affiche dans les logs. Ouvrir ce lien dans un navigateur, autoriser l'accès, copier le code de retour dans le terminal.

### Option B — Script d'authentification depuis le terminal

```bash
cd /home/guillaume/SnapForge
source venv/bin/activate

python - << 'EOF'
import sys, os
sys.path.insert(0, 'src')
os.chdir('/home/guillaume/SnapForge')
from cloud.google_photos import GooglePhotosProvider
from config import load_config, Config

config = Config(load_config())
provider = GooglePhotosProvider(config)
if provider.is_available():
    print("Authentification réussie !")
else:
    print("Authentification échouée — vérifier les logs")
EOF
```

Un URL s'affiche dans le terminal → ouvrir dans un navigateur sur votre PC → autoriser → copier le code → coller dans le terminal.

### Le token est sauvegardé

Une fois authentifié, le token est sauvegardé dans :
```
credentials/google_token.pkl
```

**Le token se renouvelle automatiquement.** L'authentification n'est nécessaire qu'une seule fois.

---

## Vérification

Après une session photo, vérifier les logs :

```bash
journalctl -u snapforge -n 20
# ou en mode manuel :
python src/app.py 2>&1 | grep -i "google\|upload\|photo"
```

Logs attendus après upload :
```
INFO  cloud.google_photos: Google Photos: https://photos.google.com/photo/...
INFO  cloud.uploader: Upload terminé : snapforge_0001_...jpg
```

---

## Note importante sur les URLs et le QR Code

> **Google Photos ne génère pas d'URL publique directe** par photo.
> L'URL retournée est uniquement accessible par le propriétaire du compte.
> **Les invités ne pourront pas télécharger la photo via le QR code** si vous utilisez l'URL Google Photos.

### Solutions recommandées

#### Option A — Serveur local (recommandé)

Les photos restent accessibles sur le réseau local du Wi-Fi de l'événement.

```yaml
qr:
  base_url: "http://ADRESSE_IP_PI/photos"
```

Activer nginx sur le Pi :
```bash
sudo apt install nginx
sudo nano /etc/nginx/sites-available/snapforge
```

```nginx
server {
    listen 80;
    location /photos {
        alias /home/guillaume/SnapForge/Photo/final;
        autoindex on;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/snapforge /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

#### Option B — Cloudflare R2 (URL publique sur internet)

```yaml
cloud:
  enabled: true
  provider: cloudflare
  cloudflare:
    account_id: "votre_account_id"
    api_token: "votre_api_token"
    bucket_name: "snapforge"
    public_url_base: "https://VOTRE_BUCKET.r2.dev"

qr:
  base_url: "https://VOTRE_BUCKET.r2.dev"
```

---

## Résumé des fichiers impliqués

| Fichier | Rôle |
|---------|------|
| `credentials/google_credentials.json` | Identifiants OAuth téléchargés depuis Google Cloud |
| `credentials/google_token.pkl` | Token d'accès généré après la première auth (automatique) |
| `src/cloud/google_photos.py` | Code de l'intégration Google Photos |
| `src/cloud/uploader.py` | Gestion de l'upload + file d'attente |
| `Photo/upload_queue.json` | File d'attente si upload échoue (réessai automatique) |

---

## Dépannage

### "Token expiré"
```bash
rm credentials/google_token.pkl
# Puis relancer l'app → réauthentification automatique
```

### "Access denied" ou "403"
- Vérifier que votre email est bien dans la liste des utilisateurs test (Étape 3)
- Vérifier que l'API Photos Library est bien activée (Étape 2)

### Upload ne se déclenche pas
- Vérifier `cloud.enabled: true` dans `config.yaml`
- Vérifier `cloud.provider: google_photos`
- Consulter les logs : `journalctl -u snapforge -n 30`

### Photos dans la file d'attente non envoyées
```bash
# Voir les uploads en attente
cat Photo/upload_queue.json

# Forcer un retry en relançant l'app
sudo systemctl restart snapforge
```
