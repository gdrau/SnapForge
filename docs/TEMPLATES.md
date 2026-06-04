# Créer un nouveau template

Un template est un fichier JSON dans `templates/`. Il définit la mise en page de l'image finale.

## Structure minimale

```json
{
  "name": "mon_template",
  "description": "Description courte",
  "width": 1800,
  "height": 1200,
  "background_color": [255, 255, 255],
  "slots": [
    { "x": 20, "y": 20, "width": 860, "height": 560 },
    { "x": 920, "y": 20, "width": 860, "height": 560 }
  ],
  "text_elements": [],
  "overlay_path": null
}
```

## Champs

| Champ              | Type          | Description                                          |
|--------------------|---------------|------------------------------------------------------|
| `name`             | string        | Identifiant unique (= nom du fichier sans `.json`)  |
| `description`      | string        | Description affichée dans les logs                  |
| `width`            | int (px)      | Largeur de l'image finale                           |
| `height`           | int (px)      | Hauteur de l'image finale                           |
| `background_color` | [R, G, B]     | Couleur de fond (0-255)                             |
| `slots`            | array         | Zones de placement des photos                       |
| `text_elements`    | array         | Textes à superposer (optionnel)                     |
| `overlay_path`     | string / null | Chemin vers image PNG RGBA à superposer (optionnel) |

### Slot

```json
{ "x": 20, "y": 20, "width": 860, "height": 560 }
```

- `x`, `y` : coin supérieur gauche en pixels
- `width`, `height` : dimensions de la zone
- La photo est automatiquement recadrée (center-crop) pour remplir la zone

### Text element

```json
{
  "text": "Soirée Mariage 2026",
  "x": 600,
  "y": 1160,
  "size": 40,
  "color": [255, 255, 255]
}
```

### Overlay PNG

Placez un PNG RGBA (transparence supportée) dans `assets/overlays/` :

```json
"overlay_path": "assets/overlays/cadre_dore.png"
```

L'overlay est redimensionné aux dimensions du template et fusionné par-dessus les photos.

## Activation du template

Dans `config.yaml` :

```yaml
templates:
  default: mon_template   # Doit correspondre au nom du fichier sans .json
  templates_dir: templates
```

## Exemple : template portrait 2 photos

```json
{
  "name": "duo_portrait",
  "description": "Deux portraits côte à côte",
  "width": 1840,
  "height": 960,
  "background_color": [30, 30, 30],
  "slots": [
    { "x":  20, "y": 20, "width": 890, "height": 920 },
    { "x": 930, "y": 20, "width": 890, "height": 920 }
  ],
  "text_elements": [
    { "text": "Mon Événement", "x": 760, "y": 10, "size": 28, "color": [200, 200, 200] }
  ]
}
```

## Conseils

- Laissez 15-20 px de marge sur les bords pour un meilleur rendu à l'impression.
- Testez avec `python scripts/test_camera.py` puis lancez manuellement une session.
- Pour des bordures entre les photos, augmentez l'écart entre les slots.
- La résolution recommandée pour l'impression A6 (10×15 cm) à 300 DPI est 1772×1181 px.
