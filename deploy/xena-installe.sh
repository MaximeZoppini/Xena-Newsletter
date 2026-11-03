#!/bin/bash
# Installation après mise à jour. Lancé par xena-update.sh une fois le code récupéré,
# pour que ce soit toujours la nouvelle version de ce fichier qui s'exécute.
set -euo pipefail
cd /opt/x-newsletter

venv/bin/pip install --quiet -r requirements.txt
install -m 644 deploy/x-newsletter.service /etc/systemd/system/x-newsletter.service
install -m 644 deploy/xena-update.service /etc/systemd/system/xena-update.service
install -m 644 deploy/xena-update.timer /etc/systemd/system/xena-update.timer
install -m 644 deploy/xena-favoris-x.service /etc/systemd/system/xena-favoris-x.service
install -m 644 deploy/xena-favoris-x.timer /etc/systemd/system/xena-favoris-x.timer
systemctl daemon-reload
systemctl enable --now --quiet xena-favoris-x.timer
systemctl restart x-newsletter
