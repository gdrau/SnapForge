# Configuration Google Photos — SnapForge

> ⚠️ **Pour partager les photos avec les invités via QR code, utilisez Cloudflare R2 à la place.**
> Google Photos génère des URLs **privées** — seul le propriétaire du compte peut y accéder.
> Voir [CONFIGURATION_CLOUDFLARE_R2.md](CONFIGURATION_CLOUDFLARE_R2.md) pour la solution recommandée.
>
> Ce guide est utile si vous souhaitez **archiver** vos photos sur Google Photos en parallèle.

---

Ce guide explique comment connecter SnapForge à votre compte Google Photos pour uploader automatiquement les photos après chaque session.

---

## Prérequis

- Un compte Google
- Accès à [console.cloud.google.com](https://console.cloud.google.com)
- Python installé sur votre PC (pour l'authentification initiale, plus simple qu'en headless)

### ⚠️ Packages obligatoires

Les packages Google ne sont **pas installés par défaut** dans le venv. À faire **avant tout** sur le Pi :

```bash
cd /home/guillaume/SnapForge
source venv/bin/activate
pip install google-auth google-auth-oauthlib
```

Sans ces packages, l'upload Google Photos ne fonctionnera pas du tout, même si tout le reste est correctement configuré.

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

> **Important** : tant que l'application est en mode "Test", seuls les utilisateurs ajoutés peuvent autoriser l'accès. C'est suffisant pour un usage personnel.

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
  provider: google_photos        # ← obligatoire, pas "local"
  retry_on_failure: true
  retry_queue_file: Photo/upload_queue.json

  google_photos:
    credentials_file: credentials/google_credentials.json
    album_name: "Mon Événement"  # nom de l'album créé automatiquement
```

### ⚠️ QR code : ne pas mettre https://photos.google.com

`https://photos.google.com` **ne fonctionne pas** comme `base_url` — Google Photos ne génère pas d'URLs publiques directes par photo.

Utiliser à la place l'IP de votre Pi (serveur local) :

```yaml
qr:
  enabled: true
  base_url: "http://ADRESSE_IP_DU_PI/photos"   # ← IP réelle du Pi
  size: 300
  display_duration: 15
```

Trouver l'IP du Pi :
```bash
hostname -I | awk '{print $1}'
```

---

## Étape 7 — Première authentification (obligatoire, une seule fois)

Le Pi n'a pas de navigateur : la méthode recommandée est d'authentifier **depuis votre PC**.

### Méthode PC (recommandée)

**Sur votre PC :**

```bash
# Installer les packages Google sur votre PC aussi
pip install google-auth google-auth-oauthlib

# Copier google_credentials.json depuis le Pi vers votre PC
scp guillaume@ADRESSE_IP:/home/guillaume/SnapForge/credentials/google_credentials.json .
```

Créer le fichier `auth_google.py` sur votre PC :

```python
# auth_google.py
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/photoslibrary.appendonly"]

flow = InstalledAppFlow.from_client_secrets_file(
    "google_credentials.json", SCOPES
)
creds = flow.run_local_server(port=0)

with open("google_token.pkl", "wb") as f:
    pickle.dump(creds, f)

print("Token sauvegardé dans google_token.pkl")
print("Copiez ce fichier vers credentials/ sur le Pi")
```

```bash
# Exécuter — un navigateur s'ouvre, se connecter, autoriser
python auth_google.py

# Copier le token généré vers le Pi
scp google_token.pkl guillaume@ADRESSE_IP:/home/guillaume/SnapForge/credentials/
```

**Vérifier sur le Pi :**

```bash
ls /home/guillaume/SnapForge/credentials/
# Doit afficher :
# google_credentials.json
# google_token.pkl     ← le token d'accès
```

### Le token est sauvegardé automatiquement

Une fois `google_token.pkl` présent sur le Pi, **aucune autre authentification n'est nécessaire**. Le token se renouvelle automatiquement.

---

## Étape 8 — Tester l'authentification

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
    print("Authentification OK ✓  — prêt pour l'upload")
else:
    print("ÉCHEC — vérifier les étapes 5 et 7 ci-dessus")
EOF
```

---

## Vérification après une session photo

```bash
# Logs en direct
journalctl -u snapforge -f

# ou en mode manuel
source venv/bin/activate
python src/app.py 2>&1 | grep -i "google\|upload"
```

Logs attendus après upload réussi :
```
INFO  cloud.google_photos: Google Photos: https://photos.google.com/photo/...
```

---

## Note importante sur les URLs et le QR Code

> **Google Photos ne génère pas d'URL publique directe** par photo.
> L'URL retournée (`productUrl`) est uniquement accessible par le propriétaire du compte Google.
> Les invités ne pourront **pas** télécharger leur photo via le QR code avec une URL Google Photos.

### Solutions pour un QR code fonctionnel pour les invités

#### Option A — Serveur local nginx (recommandé pour événements)

Les photos sont accessibles sur le réseau Wi-Fi de l'événement.

```yaml
qr:
  base_url: "http://ADRESSE_IP_DU_PI/photos"
```

Configurer nginx sur le Pi :

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
| `credentials/google_token.pkl` | Token d'accès généré à l'étape 7 (auto-renouvelé) |
| `src/cloud/google_photos.py` | Code de l'intégration Google Photos |
| `src/cloud/uploader.py` | Gestionnaire upload + file d'attente |
| `Photo/upload_queue.json` | File d'attente si upload échoue (réessai auto) |

---

## Dépannage

### "google-auth non installé" ou import error

```bash
source venv/bin/activate
pip install google-auth google-auth-oauthlib
```

### "Token expiré" ou authentification refusée

```bash
rm /home/guillaume/SnapForge/credentials/google_token.pkl
# Refaire l'étape 7 (authentification depuis le PC)
```

### "Access denied" ou "403"

- Vérifier que votre email est bien dans la liste des **utilisateurs test** (Étape 3)
- Vérifier que l'**API Photos Library est activée** (Étape 2)
- S'assurer que `google_credentials.json` correspond au bon projet Google Cloud

### Upload ne se déclenche pas

- Vérifier `cloud.enabled: true` dans `config.yaml`
- Vérifier `cloud.provider: google_photos` (pas `local`)
- Vérifier que `credentials/google_token.pkl` existe bien sur le Pi
- Consulter les logs : `journalctl -u snapforge -n 30`

### QR code pointe vers une mauvaise URL

- Ne **jamais** mettre `https://photos.google.com` comme `base_url`
- Utiliser `http://ADRESSE_IP_DU_PI/photos` + nginx (Étape 6)

### Photos dans la file d'attente non envoyées

```bash
# Voir les uploads en attente
cat /home/guillaume/SnapForge/Photo/upload_queue.json

# Forcer un retry en redémarrant le service
sudo systemctl restart snapforge
```
