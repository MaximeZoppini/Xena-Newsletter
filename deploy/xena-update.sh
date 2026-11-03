#!/bin/bash
# Déploiement continu : si master a bougé sur GitHub, on récupère, on installe et on redémarre.
# L'installation est dans xena-installe.sh : bash lit ce script au fil de l'exécution,
# donc après le reset il exécuterait encore l'ancienne version des lignes suivantes.
set -euo pipefail
cd /opt/x-newsletter

git fetch --quiet origin master
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)
[ "$LOCAL" = "$REMOTE" ] && exit 0

echo "Mise à jour ${LOCAL:0:7} -> ${REMOTE:0:7}"
git reset --hard --quiet origin/master
bash deploy/xena-installe.sh
echo "Xena redémarrée sur ${REMOTE:0:7}"
