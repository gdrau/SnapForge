# Créer et modifier les templates — SnapForge

Un template est un fichier **JSON** dans le dossier `templates/`. Il définit la mise en page de l'image finale générée après la session photo.

---

## Templates inclus

| Fichier                   | Format         | Dimensions    | Orientation |
|---------------------------|----------------|---------------|-------------|
| `portrait_1photo.json`    | 10×15 cm       | 1575×2362 px  | Portrait    |
| `landscape_4photos.json`  | 15×10 cm       | 2362×1575 px  | Paysage     |

> Résolution **400 DPI** — qualité impression maximale. JPEG à 97 % de qualité.

---

## Structure complète d'un template

```json
{
  "name": "mon_template",
  "description": "Description courte",
  "width": 1181,
  "height": 1772,
  "background": {
    "type": "color",
    "color": [248, 248, 248],
    "fallback_color": [248, 248, 248]
  },
  "slots": [
    { "x": 103, "y": 257, "width": 975, "height": 1300 }
  ],
  "title_zone": {
    "x": 40, "y": 80, "width": 1101, "height": 90,
    "size": 92, "color": [26, 26, 26], "align": "center"
  },
  "description_zone": {
    "x": 40, "y": 1590, "width": 1101, "height": 80,
    "size": 72, "color": [85, 85, 85], "align": "center"
  },
  "decorations": [],
  "overlay_path": null,
  "text_elements": []
}
```

---

## Champs détaillés

### `background`

Deux modes disponibles :

```json
"background": { "type": "color", "color": [248, 248, 248] }
```

```json
"background": {
  "type": "image",
  "path": "assets/backgrounds/mon_fond.jpg",
  "fallback_color": [248, 248, 248]
}
```

L'image est redimensionnée et recadrée pour remplir exactement le template. Si le fichier est introuvable, la couleur de fallback est utilisée.

> **Compatibilité ancienne** : le champ `background_color` (tableau RGB) est également supporté.

---

### `slots`

Zones de placement des photos. La photo est **automatiquement recadrée au centre** pour remplir exactement la zone (ratio conservé).

```json
"slots": [
  { "x": 103, "y": 257, "width": 975, "height": 1300 }
]
```

Pour 4 photos :
```json
"slots": [
  { "x":  30, "y": 115, "width": 848, "height": 468 },
  { "x": 893, "y": 115, "width": 848, "height": 468 },
  { "x":  30, "y": 598, "width": 848, "height": 468 },
  { "x": 893, "y": 598, "width": 848, "height": 468 }
]
```

> Le slot N est rempli par la photo N. Si moins de photos que de slots, les slots vides restent en couleur de fond.

---

### `title_zone` et `description_zone`

Zones de texte **dynamiques** — le contenu vient du menu admin (ou de `config.yaml`).

```json
"title_zone": {
  "x": 40, "y": 80, "width": 1101, "height": 90,
  "size": 92,
  "color": [26, 26, 26],
  "align": "center"
}
```

| Champ   | Description                        |
|---------|------------------------------------|
| `x, y`  | Position du coin supérieur gauche  |
| `width, height` | Dimensions de la zone        |
| `size`  | Taille police en points (à 400 DPI : ≈ 60–120 pour un titre lisible) |
| `color` | Couleur RGB [R, G, B]              |
| `align` | `"center"`, `"left"`, ou `"right"` |

Le texte est automatiquement tronqué s'il dépasse la largeur de la zone.

> La police utilisée pour `title_zone` et `description_zone` est `processing.font_path` dans `config.yaml` (distinct de `app.font_path` qui s'applique à l'interface Pygame). Si `processing.font_path` est absent, la valeur de `app.font_path` est utilisée en fallback.

---

### `decorations`

Éléments graphiques statiques (lignes, rectangles).

```json
"decorations": [
  { "type": "line", "x1": 40, "y1": 152, "x2": 1141, "y2": 152, "color": [255, 140, 0], "width": 4 },
  { "type": "rect", "x": 40, "y": 1640, "w": 1101, "h": 6, "color": [200, 200, 200] }
]
```

---

### `overlay_path`

Fichier PNG RGBA superposé par-dessus toutes les photos (cadre, filigrane…) :

```json
"overlay_path": "assets/overlays/cadre_dore.png"
```

Le PNG est redimensionné aux dimensions du template. La transparence est respectée.

---

### `text_elements`

Textes **statiques** (ne changent pas entre sessions) :

```json
"text_elements": [
  { "text": "© SnapForge 2026", "x": 500, "y": 1740, "size": 24, "color": [180, 180, 180] }
]
```

---

## Activation d'un template

Dans `config.yaml`, mapper chaque nombre de photos à son template :

```yaml
templates:
  photo_1: portrait_1photo
  photo_2: portrait_1photo
  photo_3: portrait_1photo
  photo_4: landscape_4photos
  default: portrait_1photo
  templates_dir: templates
```

**Depuis le menu admin (ESC → Photos/Templates)** : les templates disponibles peuvent être assignés directement sans modifier le fichier YAML.

> Pour le **GIF paysage**, le crop des frames utilise le ratio du canvas du template (`width/height`), pas les dimensions des slots individuels. Exemple : `landscape_4photos` a un canvas 2362×1575 (ratio 3:2 ≈ 1,5:1) — chaque frame GIF est recadrée à ce ratio avant animation.

---

## Calcul des dimensions pour l'impression

| Format papier         | DPI | Dimensions pixels |
|-----------------------|-----|-------------------|
| 10×15 cm (A6)         | 400 | 1575×2362 px ✅   |
| 15×10 cm (A6 paysage) | 400 | 2362×1575 px ✅   |
| 10×15 cm (A6)         | 300 | 1181×1772 px      |
| 15×10 cm (A6 paysage) | 300 | 1772×1181 px      |
| 13×18 cm              | 300 | 1535×2126 px      |
| 9×13 cm               | 300 | 1063×1535 px      |

Formule : `px = cm ÷ 2.54 × DPI`

**Marges de sécurité** : laisser 20 px de marge sur les bords pour l'impression.

---

## Exemple : template duo portrait (2 photos)

```json
{
  "name": "duo_portrait",
  "description": "2 portraits côte à côte sur fond blanc",
  "width": 1772,
  "height": 1181,
  "background": { "type": "color", "color": [250, 250, 248] },
  "slots": [
    { "x":  20, "y": 100, "width": 860, "height": 980 },
    { "x": 892, "y": 100, "width": 860, "height": 980 }
  ],
  "title_zone": {
    "x": 20, "y": 10, "width": 1732, "height": 78,
    "size": 64, "color": [30, 30, 30], "align": "center"
  },
  "description_zone": {
    "x": 20, "y": 1092, "width": 1732, "height": 70,
    "size": 36, "color": [100, 100, 100], "align": "center"
  },
  "decorations": [],
  "text_elements": []
}
```

Sauvegarder sous `templates/duo_portrait.json`, puis dans `config.yaml` :

```yaml
templates:
  photo_2: duo_portrait
```
