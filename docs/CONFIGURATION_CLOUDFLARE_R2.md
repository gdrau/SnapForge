# Configuration Cloudflare R2 — SnapForge

Cloudflare R2 est le stockage objet de Cloudflare. C'est la solution recommandée pour SnapForge car :

- **URLs publiques** → les invités peuvent télécharger leur photo sans compte
- **Gratuit jusqu'à 10 Go** et 1 million de requêtes/mois
- **Rapide** (~1-3 s d'upload en Wi-Fi)
- **Mondial** → accessible partout avec connexion internet
- **Simple à configurer** → pas d'OAuth, juste un token

---

## Prérequis

- Un compte Cloudflare gratuit sur [cloudflare.com](https://cloudflare.com)
- Le package `requests` (déjà dans `requirements.txt`)

---

## Étape 1 — Créer un compte Cloudflare

1. Aller sur [cloudflare.com](https://cloudflare.com)
2. **Sign Up** → entrer email et mot de passe
3. Vous n'avez pas besoin d'un domaine, R2 fonctionne sans

---

## Étape 2 — Créer un bucket R2

1. Dans le dashboard, menu gauche → **R2 Object Storage**
2. Cliquer **"Create bucket"**
3. **Bucket name** : `snapforge` (tout en minuscules, pas d'espaces)
4. **Location** : choisir la région la plus proche de vous
5. Cliquer **"Create bucket"**

---

## Étape 3 — Activer l'accès public

1. Cliquer sur votre bucket `snapforge`
2. Onglet **"Settings"**
3. Section **"Public Access"** → cliquer **"Allow Access"**
4. Confirmer → **"Allow"**
5. Un URL apparaît dans la forme `https://pub-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX.r2.dev`

> ⚠️ **Copier cet URL** — vous en aurez besoin dans config.yaml

---

## Étape 4 — Créer un token API R2

> **Note interface Cloudflare** : "Cloudflare R2 Storage" n'apparaît pas dans la catégorie "Account". Utilisez le template ou la méthode R2 directe ci-dessous.

### Méthode A — Template (la plus simple ✅)

1. En haut à droite → **Mon profil** → onglet **"API Tokens"**
2. Cliquer **"Create Token"**
3. Trouver le template **"Edit Cloudflare Workers"** → cliquer **"Use template"**
4. Ce template inclut automatiquement `Workers R2 Storage - Edit`
5. Scroller vers le bas → **"Continue to summary"** → **"Create Token"**
6. **Copier le token** — affiché une seule fois !

---

### Méthode B — Depuis la page R2 directement

1. Dashboard → **R2 Object Storage**
2. En haut à droite de la page R2 → bouton **"Manage R2 API Tokens"**
3. Cliquer **"Create API Token"**
4. Nom : `SnapForge`
5. Permissions : **Object Read & Write**
6. Cliquer **"Create API Token"**
7. Vous obtenez un **Access Key ID** et un **Secret Access Key**

> ⚠️ **Méthode B** génère des credentials S3-compatible (pas un Bearer token).
> Elle nécessite une configuration différente — préférez la **Méthode A** pour SnapForge.

---

### Méthode C — Token personnalisé (si les deux autres échouent)

1. API Tokens → **"Create Token"** → **"Create Custom Token"**
2. **Token name** : `SnapForge R2`
3. Section **"Permissions"** → cliquer **"Add more"** → dans le champ de recherche, taper **`r2`** (pas "account")
4. Sélectionner **"Workers R2 Storage"** → **"Edit"**
5. **"Continue to summary"** → **"Create Token"**
6. **Copier le token**

---

## Étape 5 — Récupérer votre Account ID

1. Dashboard Cloudflare → page d'accueil ou n'importe quelle page
2. Dans la **colonne de droite** → section **"Account ID"**
3. Copier cet identifiant (suite de lettres et chiffres)

---

## Étape 6 — Configurer config.yaml

Ouvrir `/home/guillaume/SnapForge/config.yaml` :

```yaml
cloud:
  enabled: true
  provider: cloudflare                  # ← cloudflare
  retry_on_failure: true
  retry_queue_file: Photo/upload_queue.json

  cloudflare:
    account_id: "abc123def456..."       # ← votre Account ID (étape 5)
    api_token:  "votre_token_api_r2"    # ← votre token (étape 4)
    bucket_name: "snapforge"            # ← nom du bucket (étape 2)
    public_url_base: "https://pub-XXXX.r2.dev"  # ← URL publique (étape 3)

qr:
  enabled: true
  base_url: "https://pub-XXXX.r2.dev"  # ← même URL que public_url_base
  use_upload_url: true                  # ← IMPORTANT : utiliser l'URL Cloudflare
  size: 300
  display_duration: 15
```

> ⚠️ `use_upload_url: true` est **obligatoire** avec Cloudflare pour que le QR code pointe vers l'URL publique R2 et non une URL locale.

---

## Étape 7 — Tester l'upload

```bash
cd /home/guillaume/SnapForge
source venv/bin/activate

python - << 'EOF'
import sys, os
sys.path.insert(0, 'src')
os.chdir('/home/guillaume/SnapForge')
from cloud.cloudflare import CloudflareProvider
from config import load_config, Config

config   = Config(load_config())
provider = CloudflareProvider(config)

if not provider.is_available():
    print("ERREUR : configuration incomplète (account_id, api_token ou bucket_name manquant)")
else:
    print("Configuration OK ✓")
    # Test d'upload avec un petit fichier
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.write(b"test")
    tmp.close()
    url = provider.upload(tmp.name, "test_snapforge.jpg")
    os.unlink(tmp.name)
    if url:
        print(f"Upload OK ✓\nURL : {url}")
        print("Ouvrez cette URL dans un navigateur pour vérifier l'accès public")
    else:
        print("ERREUR upload — vérifier les logs ci-dessus")
EOF
```

---

## Vérification après une session photo

Après avoir pris une photo avec SnapForge, les logs doivent afficher :

```
INFO  cloud.cloudflare: Cloudflare R2 upload OK : https://pub-XXXX.r2.dev/snapforge_0001_...jpg
INFO  state_machine: QR = URL cloud : https://pub-XXXX.r2.dev/snapforge_0001_...jpg
```

Scannez le QR code avec un téléphone → la photo doit s'ouvrir directement dans le navigateur.

---

## Résumé de la configuration complète

```yaml
# config.yaml — configuration Cloudflare R2 complète

cloud:
  enabled: true
  provider: cloudflare
  retry_on_failure: true
  retry_queue_file: Photo/upload_queue.json
  cloudflare:
    account_id: "VOTRE_ACCOUNT_ID"
    api_token:  "VOTRE_TOKEN_API"
    bucket_name: "snapforge"
    public_url_base: "https://pub-XXXX.r2.dev"

qr:
  enabled: true
  base_url: "https://pub-XXXX.r2.dev"
  use_upload_url: true
  size: 300
  display_duration: 15

plugins:
  qr_on_result: true
```

---

## Fichiers impliqués

| Fichier | Rôle |
|---------|------|
| `src/cloud/cloudflare.py` | Implémentation de l'upload R2 |
| `src/cloud/uploader.py`   | Gestion upload + file d'attente retry |
| `Photo/upload_queue.json` | File d'attente si upload échoue (réessai auto) |

---

## Dépannage

### "Cloudflare R2 non configuré"

Vérifier que `account_id`, `api_token`, `bucket_name` et `public_url_base` sont tous renseignés dans `config.yaml`.

### "403 Forbidden" ou "401 Unauthorized"

- Vérifier que le token a bien la permission `Cloudflare R2 Storage - Edit`
- Vérifier que `account_id` est correct (colonne droite du dashboard)
- Régénérer un nouveau token si besoin

### "404 Not Found" ou erreur bucket

- Vérifier que `bucket_name` correspond exactement au nom créé sur Cloudflare
- Respecter la casse (tout en minuscules recommandé)

### Le QR code s'affiche mais la photo est inaccessible

- Vérifier que l'accès public est bien activé sur le bucket (Étape 3)
- Vérifier que `public_url_base` correspond à l'URL affichée dans les paramètres du bucket
- Vérifier `use_upload_url: true` dans la section `qr`

### Photos dans la file d'attente non envoyées

```bash
cat /home/guillaume/SnapForge/Photo/upload_queue.json

# Forcer un retry
sudo systemctl restart snapforge
```

---

## Coûts Cloudflare R2 (plan gratuit)

| Ressource | Limite gratuite |
|-----------|----------------|
| Stockage | 10 Go / mois |
| Opérations classe A (upload) | 1 million / mois |
| Opérations classe B (téléchargement) | 10 millions / mois |
| Bande passante sortante | **Gratuit** (pas de frais de sortie) |

Pour un photobooth événementiel (quelques centaines de photos de quelques Mo chacune), le plan gratuit est largement suffisant.
