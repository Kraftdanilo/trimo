# CARTON — Architecture d'interface éditeur

> Comment la structure d'un éditeur vidéo décrite par les recommandations se
> traduit dans CARTON — un studio de cartons typographiques animés.
> Ce document est la référence UI/UX et la feuille de route.

## 1. Vue d'ensemble

CARTON suit la structure canonique d'un éditeur (UI/UX + moteur) :

```
┌──────────────────────────────────────────────────────────────┐
│ Logo │ Projet (nom) │            Réalisation IA │ PNG │ ⤓     │
├──────────┬───────────────────────────────┬───────────────────┤
│ MÉDIAS/  │        PRÉVISUALISATION       │   RÉALISATION IA  │
│ SÉQUENCE │   (Viewport / Preview panel)  │  (agent directeur)│
│ + LISTE  │   canvas 1920×1080 · 16:9     │  directive → JSON │
├──────────┴───────────────────────────────┴───────────────────┤
│                    TIMELINE                                  │
│  règle graduée · blocs de scènes · playhead · scrub          │
├──────────────────────────────────────────────────────────────┤
│ ▶ Loop │ 00:12.0 / 00:45.0 │ raccourcis                      │
└──────────────────────────────────────────────────────────────┘
```

## 2. Correspondance recommandation ↔ CARTON

| Concept (recommandation) | Dans CARTON | État |
|---|---|---|
| **Viewport / preview panel** | `#stage` — canvas 1920×1080 16:9, playhead, scrub | ✅ |
| **Timeline** | `#timeline` — règle, blocs de scènes, playhead, scrub | ✅ |
| **Inspecteur** | `#props` — propriétés de la scène sélectionnée | ✅ |
| **Bibliothèque de médias** | `#sceneList` (séquence) — variante « bibliothèque de cartons » | ✅ |
| **Barre d'outils / transport** | `#btnStart`, `#btnPlay`, `#btnLoop`, timecode | ✅ |
| **Export** | modale export (WebM progressif, PNG) | ✅ |
| **Undo/redo** | versions IA archivées (rollback) + Ctrl+Z/Ctrl+Y global | ✅ |
| **Grilles et guides** | `drawGuides()` + sélecteur (off/tiers/centre/grille) + touche G | ✅ |
| **Zoom timeline / viewport** | zoom timeline par molette + ctrl, zoom viewport par taille de fenêtre | ✅ |
| **Ratios d'image (9:16, 1:1)** | sélecteur de ratio dans les méta du stage | ✅ |
| **Bibliothèque de modèles** | `TEMPLATES` + volet Bibliothèque (presets de séquences) | ✅ |
| **Moteur audio** | — | ⬜ hors périmètre (v2) |

## 3. Le clip « CARTON »

La structure de clip recommandée (`startTime, duration, source, position…`)
correspond au modèle `scene` de CARTON :

```js
// Scene ≈ Clip
{
  text, anim, font, size, duration,
  color, bg, tracking, posY, align, grain, seed
}
// startTime est dérivé : cumul des durées des scènes précédentes
// (fonction sceneAt(project, t) résout le playhead → scène active)
```

## 4. Design system (à respecter pour toute évolution UI)

- **Couleurs** : fond sombre neutre, un accent unique (jaune carton), états
  actifs/inactifs nets (classe `.on`).
- **Typographie** : polices du studio (Anton, Archivo, Bebas…) côté création ;
  interface en police système compacte, hiérarchie par graisse et casse.
- **Icônes** : Lucide uniquement, cohérence 1 bouton = 1 icône + label.
- **Espacements** : grille serrée type NLE (dense, bordures 1px, panneaux
  séparés par des lignes, pas de gros blocs flottants).
- **Animations** : micro-transitions (< 150 ms), jamais de décoration gratuite
  — l'animation spectaculaire appartient au canvas, pas au chrome.
- **Thème** : sombre par défaut (usage studio), clair en option future.
- **Règle d'or** : l'utilisateur doit voir en permanence le lien
  **sélection dans la liste ↔ bloc en timeline ↔ rendu dans le viewport**.

## 5. Feuille de route

1. ✅ **Undo/redo global** (Ctrl+Z / Ctrl+Y sur l'état projet) — fait.
2. ✅ **Guides & grilles** activables — fait (off / tiers / centre / grille, touche G).
3. ✅ **Zoom timeline** (molette + ctrl) — fait.
4. ✅ **Sélecteur de ratio** (16:9 / 9:16 / 1:1) — fait.
5. ✅ **Bibliothèque de modèles** — fait : volet « Bibliothèque » dans la barre
   latérale, catalogue `TEMPLATES` (6 presets : annonce, promo café, générique,
   stats, avertissement, poème). Chaque preset passe par `normalizeProject`
   (mêmes garanties qu'un projet IA) ; application archivée dans l'undo.
6. (v2, hors périmètre actuel) : audio, import médias externes, export FFmpeg.
