# Pharmacie proche

Application web installable (PWA) qui montre la pharmacie **ouverte** la plus proche, avec l'appel et l'itinéraire en un geste.

- Les horaires sont calculés à l'heure de Paris, jours fériés compris (pause déjeuner, passage de minuit, 24 h/24).
- Fonctionne hors connexion pour les zones déjà consultées.
- Pour la nuit, le dimanche et les jours fériés, renvoie vers le 3237 et 3237.fr. La liste officielle des pharmacies de garde n'existe pas en données ouvertes : l'appli n'affirme jamais qu'une pharmacie est « de garde ».

**Installer sur iPhone** : ouvrir le site dans Safari, toucher Partager, puis « Sur l'écran d'accueil ».

## Comment ça marche

Un site statique, sans serveur ni compte.

| Élément | Rôle |
|---|---|
| `index.html` | Toute l'application (interface + lecteur d'horaires `opening_hours`) |
| `sw.js` | Mode hors connexion, cache des zones consultées |
| `scripts/build_pharmacies.py` | Télécharge les pharmacies d'OpenStreetMap, complète les adresses (Géoplateforme IGN) et écrit des tuiles `data/p/<ligne>_<colonne>.json` (cases de 0,2°) |
| `.github/workflows/pages.yml` | Régénère les tuiles chaque dimanche et publie sur GitHub Pages |

Si une zone n'a pas de tuile, l'appli interroge Overpass en direct (plusieurs miroirs en parallèle).

## Vie privée

La position reste sur l'appareil. Le site ne reçoit que les tuiles de la zone (cases d'environ 20 km). Le texte tapé dans la barre de recherche est envoyé au service d'adresses de l'IGN (`data.geopf.fr`).

## Limites

Les horaires viennent d'OpenStreetMap : ils peuvent être périmés ou absents. Appelez avant de vous déplacer. En cas d'urgence vitale : 15 ou 112.

## Données

© contributeurs [OpenStreetMap](https://www.openstreetmap.org/copyright), licence ODbL. Adresses : Géoplateforme (IGN).
