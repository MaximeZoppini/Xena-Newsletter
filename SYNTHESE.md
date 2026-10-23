# Xena — module Synthèse 12 h

> Spécification cible, à lire avec [MISSION.md](MISSION.md).

**Objectif** : deux fois par jour, produire une phrase à retenir, les points qui la justifient, et le delta depuis la synthèse précédente. La qualité visée est celle d'un analyste qui a lu tout le flux, recoupé, trié le vrai du faux, et qui sait ce qui ne s'est pas passé.

Le module s'exécute en cinq passes. Les passes 1 à 3 tournent sur un modèle rapide, item par item ou cluster par cluster. Les passes 4 et 5 tournent sur le modèle le plus fort disponible, avec tout le contexte.

| Passe | Rôle | Modèle | Appels |
| --- | --- | --- | --- |
| 1 | Fiche par item | rapide | 1 par item |
| 2 | Regroupement par cause racine | rapide | sur l'ensemble des fiches |
| 3 | Importance | rapide | 1 par cluster |
| 4 | Synthèse | fort | 1, contexte complet |
| 5 | Contradicteur | fort | 1 (+ relance unique de la passe 4) |

---

## Passe 1 — Fiche par item

*Modèle rapide, 1 appel par item.*

Pour chaque article, post ou advisory collecté depuis la dernière synthèse, produire une fiche JSON :

- `faits` : liste de propositions factuelles, une par ligne, sans adjectif. Séparer explicitement ce que la source *affirme* de ce qu'elle *rapporte d'autrui*.
- `entites` : produits, versions, CVE, organisations, personnes, lieux.
- `source` : nom, niveau (1 primaire / 2 chercheur ou firme reconnue / 3 presse sérieuse / 4 réseau social), lien.
- `confiance` : 0-1, avec la raison en une phrase.
- `signaux_bruit` : appels à l'engagement, prédictions, émojis d'alerte sans source, affirmations invérifiables. Si présents, plafonner la confiance à 0,3.
- `horodatage` : première apparition.

Ne pas résumer. Ne pas interpréter. Une fiche est un relevé.

---

## Passe 2 — Regroupement par cause racine

*Modèle rapide, sur l'ensemble des fiches.*

Regrouper les fiches en clusters. La question à poser explicitement : *quels items sont le même événement vu sous des angles différents ?* Un compromis de CA qui provoque des mises à jour dans Java, Python, Go et Node est **un** cluster, pas quatre. Une rumeur et son démenti sont le même cluster.

Pour chaque cluster : nom, cause racine, items membres, statut global (confirmé / allégué / démenti / contradictoire), et, s'il prolonge un dossier vivant existant, son identifiant.

Si un cluster ne contient que des sources de niveau 4, le marquer `non_sourcé` et chercher activement une source de niveau 1-3 avant la passe 3. S'il n'y en a pas après le délai de tolérance, le cluster est conservé uniquement pour la section « Faux ou non confirmé ».

---

## Passe 3 — Importance

*Modèle rapide, par cluster.*

Trois scores de 0 à 1, chacun justifié en une phrase :

- `impact` : effet sur Maxime, ses systèmes, ses projets. Un composant de sa watchlist touché = impact élevé par défaut.
- `fenetre_action` : dans combien de temps doit-il agir, s'il le doit. Heures = 1, jours = 0,5, jamais = 0.
- `confiance` : héritée des fiches, pondérée par la corroboration.

Puis une ligne : *que ferait Maxime différemment en sachant ça ?* Si la réponse est « rien » et que le sujet ne nourrit pas sa réflexion, le cluster descend en digest.

---

## Passe 4 — Synthèse

*Modèle fort, 1 appel, contexte complet.*

**Entrées** : tous les clusters scorés, les trois dernières synthèses, les dossiers vivants ouverts, la watchlist, la liste de questions négatives.

**Avant d'écrire**, répondre obligatoirement aux questions négatives :

- Y a-t-il des dégâts réels constatés, pas seulement des failles publiées ?
- Une exploitation massive est-elle confirmée par une source de niveau 1-2 ?
- Un composant de la watchlist est-il touché sans correctif disponible ?
- Qu'est-ce que le flux présente comme nouveau et qui ne l'est pas ?
- Quelle panique du jour repose sur un seul événement compté plusieurs fois ?
- Qu'est-ce qui a été démenti depuis la dernière synthèse ?

**Puis produire** :

1. **La phrase.** Une seule. Elle doit être vraie, mémorisable, et contenir le jugement : pas « il y a eu des failles » mais « encore le bordel en cyber, sans dégâts majeurs, et la moitié de la panique est un seul incident ». Elle doit tenir compte de la synthèse précédente : « encore », « toujours », « première fois », « retour au calme » sont des mots qui exigent la mémoire.
2. **Action** : ce que Maxime doit faire dans les 12 h, ou « rien ».
3. **Confirmé** : 3 à 7 points, un par cluster important, avec la source qui fait foi.
4. **Faux ou non confirmé** : ce qui circule et ne tient pas, avec la raison.
5. **Delta** : ce qui a changé depuis la synthèse précédente, uniquement.
6. **Ce qui ne se passe pas** : une ou deux lignes issues des questions négatives, quand elles portent une information.
7. **À creuser** : 1 à 3 liens longs si un sujet mérite réflexion.

**Ton** : direct, pas d'adjectifs d'intensité non justifiés, pas de « breaking », pas de citation de plus de quelques mots.
**Longueur** : lisible en deux minutes un jour calme, cinq minutes un jour chargé. Le volume suit le monde.

---

## Passe 5 — Contradicteur

*Modèle fort, 1 appel, voit la sortie de la passe 4 et les clusters.*

Rôle : Maxime, de mauvaise humeur, qui a passé la soirée sur X. Poser :

- Qu'est-ce que tu as raté ? Vérifier chaque cluster à impact ≥ 0,5 absent de la synthèse.
- Qu'est-ce que tu as surévalué ? Chercher les items à confiance < 0,5 présentés comme confirmés.
- As-tu compté deux fois le même événement ?
- Ta phrase serait-elle fausse si un seul fait changeait ? Lequel ?
- Un lecteur qui ne verrait que ta phrase serait-il plus calme ou plus affolé que la réalité ne le justifie ?

**Sortie** : liste de corrections. Si elle n'est pas vide, la passe 4 est relancée une fois, avec les corrections en entrée. Les corrections sont journalisées dans le gap log, avec la raison, pour recalibrer les seuils.

---

## Mémoire

- Chaque synthèse est stockée avec ses clusters et ses scores.
- Chaque événement important devient un dossier vivant : historique, statut, delta à chaque synthèse, fermé quand il n'a plus bougé depuis sept jours.
- Le gap log accumule : items ratés, fausses alertes, corrections du contradicteur, retours explicites de Maxime. Il est relu par la passe 4 une fois par semaine pour ajuster ce que « important » veut dire.

---

## Réglages côté agent

- La liste de questions négatives doit être **éditable sans toucher au code**.
- Le contradicteur doit pouvoir être **désactivé**, pour comparer la qualité avec et sans (il devrait vite justifier son coût).

---

## État de l'implémentation (`synthese.py`)

Fait, avec ces choix :

- **Passe 1** : la fiche est produite par l'analyseur au fil de l'eau (un seul appel par item, déjà nécessaire pour la notation). Un signal de bruit plafonne la confiance à 0,3. Le niveau de la source vient de `config.py`.
- **Passe 2** : un appel sur l'ensemble des fiches de la période, hors thème « autre ». Une fiche oubliée par le modèle forme son propre cluster. Le dossier vivant, la confiance (corroboration entre sources indépendantes), la première apparition et la première confirmation sont calculés sans modèle.
- **Passe 3** : regroupée par lots de 25 clusters plutôt qu'un appel par cluster, pour le coût.
- **Passes 4 et 5** : comme spécifié. Les liens absents des clusters sont retirés de la sortie. Les corrections du contradicteur vont au gap log, et la phrase d'avant correction reste visible pour comparer.
- **Gap log** : relu à chaque synthèse (7 derniers jours) plutôt qu'une fois par semaine.
- **Dossiers** : fermés après 7 jours sans mouvement.
- **Réglages** : questions négatives, composants critiques, profil et contradicteur on/off sont modifiables depuis ⚙︎ sur le site.

Pas encore fait :

- La recherche active d'une source de niveau 1-3 pour un cluster `non_sourcé` : aucune source de niveau 4 (réseaux sociaux) n'est encore collectée.
- Les alertes immédiates (push Telegram) et la réputation des sources apprise sur leur historique.
