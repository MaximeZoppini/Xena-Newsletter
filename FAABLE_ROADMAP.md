# 🎯 Vision Produit, Marque & Roadmap — Xena

> **Document de cadrage stratégique basé sur le retour d'expérience de Faable.**  
> Ce document définit l'identité de marque, les lignes rouges éthiques/légales, l'architecture produit et la feuille de route technique pour transformer Xena d'un outil de veille personnel en un véritable média d'investigation de référence.

---

## 🧭 1. L'Identité de Marque : Xena

### La Promesse de Marque
> **"Xena · IA d'investigation. Je lis les enquêtes, je te donne le fait, la source et la réponse de l'accusé. Pas d'avis, jamais."**

Le mot **"jamais"** est la clé de voûte. Aucun média traditionnel ne peut tenir cette promesse, car ils sont tous soumis à des lignes éditoriales humaines. Une IA le peut.

### Règle d'or : Ton vs Fond
- **Dans le ton** : Xena est directe, curieuse, passionnée par la vérité brute, allergique au bruit médiatique et aux polémiques futiles (*"Pendant que tout le monde débattait du robot-chien, Disclose sortait ça"*).
- **Dans le fond** : Neutralité chirurgicale absolue. **Zéro avis, zéro adjectif subjectif, zéro parti pris politique.** Le fait est sec, sourcé, vérifiable, avec la version de la partie mise en cause.
- **Si un jour Xena donne son avis personnel sur le fond d'une affaire, elle perd toute sa valeur.**

### Règle de Transparence sur les Réseaux Sociaux (X / Twitter)
1. **Label Automated** : Badge officiel de compte automatisé activé sur X.
2. **Bio explicite** : Assume à 100% son identité d'IA lisant des centaines d'enquêtes par jour.
3. **Avatar stylisé** : Illustration/avatar graphique reconnaissable, jamais de photo faussement humaine trompeuse.

---

## 🚫 2. Les Lignes Rouges Éthiques & Légales

Pour bâtir un média irréprochable et pérenne :
1. **Zéro Polymarket / Paris** : Polymarket est totalement exclu. Xena ne relaye aucun marché spéculatif de paris.
2. **Respect absolu des médias d'origine & Paywalls** : Aucun contournement technique de paywalls. Xena travaille sur les flux publics légitimes, résumés officiels et accès autorisés.
3. **Zéro violation de Copyright sur les images** : Fin de la réutilisation des photos de presse d'autrui (`og:image`). Xena génère ses **propres cartes graphiques signatures** avec sa charte visuelle (fond sombre, typographie forte, source, score et fait marquant).

---

## 🗺️ 3. Roadmap Technique & Produit

### Phase 1 : La Boucle d'Apprentissage Éditoriale (Priorité 1)
- **Log des décisions humaines** : Sous chaque alerte Telegram, boutons interactifs :
  - `[ ✅ Validé / Publié ]`
  - `[ ❌ Rejeté ]`
  - `[ ✏️ Modifié ]`
- **Dataset propriétaire** : Enregistrement de chaque choix dans une table SQLite `editorial_feedback`.
- **Amélioration continue** : Utilisation de ce dataset pour recalibrer les seuils, injecter des exemples réels (*few-shot*) dans le prompt Gemini et stabiliser le jugement.

### Phase 2 : Identité Visuelle Signature (Générateur de Cartes)
- Génération automatique d'une carte image 16:9 au format de la marque :
  - Palette sombre signature (`#0d1117`).
  - Badge de certification : `XENA • IA D'INVESTIGATION`.
  - Source mise en valeur (`[MEDIAPART]`, `[DISCLOSE]`, etc.).
  - Citation textuelle factuelle avec score de pertinence.
  - Image attachée au post Telegram et prête pour X.

### Phase 3 : Déduplication Sémantique & Clustering Multi-Sources
- Embeddings vectoriels légers (`all-MiniLM` ou Gemini Embeddings).
- **Bonus de preuve multi-sources** : Si 2 ou 3 médias indépendants sortent simultanément sur le même fait, le score de preuves augmente automatiquement (+2 points) et la formule devient : *"Selon Mediapart, confirmé par Le Monde..."*.

### Phase 4 : Débat Contradictoire Procureur / Défenseur
- Réservé aux articles à fort potentiel ($\ge 7.5/10$).
- **Agent Procureur** : Isole les allégations et les documents.
- **Agent Défenseur** : A pour mission d'extraire ou de rechercher la réponse officielle de l'accusé.
- **Agent Juge** : Synthétise le fait impartial et arbitre la note finale.

### Phase 5 : Sécurité & Anti-Prompt-Injection
- Les flux RSS sont traités comme des données non fiables (`<untrusted_source_content>`).
- Validation stricte du schéma JSON de sortie.
- Demande explicite à l'IA de citer la phrase exacte de l'article pour chaque fait afin de garantir 0 hallucination.

### Phase 6 : Distribution Multi-Plateforme & Site Archive
- **Bluesky & Mastodon** : Publication automatique après validation via API gratuites.
- **Site Web Archive & Transparence** : Page web publique pour chaque alerte expliquant la note et la méthodologie (*"Pourquoi 8.4/10 ?"*).
- **Rendez-vous dominical** : Le récapitulatif des 5 enquêtes majeures de la semaine.
