# x-newsletter 🗞️🤖

Curateur d'actualité automatisé pour X (Twitter) et Discord, axé sur les médias indépendants, les enquêtes, la tech, la cybersécurité et les marchés de prédiction (Polymarket).
Une IA (Google Gemini 2.5 Flash / Google AI Studio) analyse les dépêches pour extraire le fait brut vérifié, identifier le cadrage idéologique/éditorial d'origine, et générer un tweet impartial et percutant avec un lien 1-clic.

## Architecture

- **Hébergement** : Conteneur LXC Dédié (CT 104 `x-newsletter`, Debian 12, 1.5 Go RAM) sur Proxmox.
- **Sources intégrées** :
  - *Investigation & Indépendants* : Mediapart, Disclose, Reporterre, ProPublica.
  - *Tech & Cyber* : Hacker News (Top stories Firebase), 404 Media, Ars Technica, BleepingComputer.
  - *Marchés de prédiction* : Polymarket Gamma API (cotes et volumes 24h).
- **Déduplication** : SQLite avec calcul d'empreinte SHA-256 et statut glissant.
- **Analyse d'impartialité & Synthèse** : Modèle Gemini 2.5 Flash avec contraintes JSON strictes et score de pertinence (seuil $\ge 7/10$).
- **Publication** : Envoi sur Discord (Rich Embed avec fait brut, cadrage source, tweet généré) et bouton **[TWEETER EN 1 CLIC]** ouvrant l'intention native Twitter.

## Fichiers du projet

- `config.py` : Paramètres et registre des sources RSS/APIs avec leur contexte éditorial.
- `sources.py` : Moissonneurs RSS, Hacker News et Polymarket.
- `storage.py` : Base SQLite pour l'historique et la déduplication.
- `analyzer.py` : Intégration Google GenAI (AI Studio) & prompt d'impartialité.
- `notifier.py` : Formatage Discord Webhook avec Embed et lien d'intention X.
- `main.py` : Point d'entrée CLI et boucle de veille continue.
- `x-newsletter.service` : Service systemd pour exécution 24/7 sur CT 104.

## Commandes utiles

```bash
# Tester l'ingestion des sources (sans IA)
python main.py --test-sources

# Tester l'envoi d'un message fictif sur Discord
python main.py --test-discord

# Exécuter un cycle à blanc (dry-run)
python main.py --dry-run

# Exécuter un cycle unique
python main.py --once

# Lancer la boucle de veille continue
python main.py
```

## Configuration `.env`

Créer un fichier `.env` avec :
```ini
GEMINI_API_KEY=AIzaSy...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
POLL_INTERVAL_MINUTES=20
MIN_INTEREST_SCORE=7
```
