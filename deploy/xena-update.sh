#!/bin/bash
# Déploiement continu : si master a bougé sur GitHub, on récupère, on installe et on redémarre.
set -euo pipefail
cd /opt/x-newsletter

git fetch --quiet origin master
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)
[ "$LOCAL" = "$REMOTE" ] && exit 0

echo "Mise à jour ${LOCAL:0:7} -> ${REMOTE:0:7}"
git reset --hard --quiet origin/master
venv/bin/pip install --quiet -r requirements.txt
install -m 644 deploy/x-newsletter.service /etc/systemd/system/x-newsletter.service
install -m 644 deploy/xena-update.service /etc/systemd/system/xena-update.service
install -m 644 deploy/xena-update.timer /etc/systemd/system/xena-update.timer
install -m 644 deploy/xena-favoris-x.service /etc/systemd/system/xena-favoris-x.service
install -m 644 deploy/xena-favoris-x.timer /etc/systemd/system/xena-favoris-x.timer
systemctl daemon-reload
systemctl enable --now --quiet xena-favoris-x.timer
systemctl restart x-newsletter
echo "Xena redémarrée sur ${REMOTE:0:7}"
