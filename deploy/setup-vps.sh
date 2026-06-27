#!/usr/bin/env bash
# Установка AI Web Scout на чистый Ubuntu 22.04/24.04 VPS.
# Запускать от root:  bash setup-vps.sh
set -euo pipefail

REPO="${REPO:-https://github.com/Sanheat/ai-web-scout-v.3.git}"
APP_DIR=/opt/ai-web-scout

echo "==> Пакеты"
apt-get update
apt-get install -y python3 python3-venv python3-pip git nginx \
                   gcc libxml2-dev libxslt1-dev

echo "==> Пользователь scout"
id scout >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin scout

echo "==> Код в $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull
else
    git clone "$REPO" "$APP_DIR"
fi

echo "==> venv + зависимости"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "==> Конфиг окружения"
if [ ! -f "$APP_DIR/scout.env" ]; then
    cp "$APP_DIR/deploy/scout.env.example" "$APP_DIR/scout.env"
    echo "!!! Отредактируйте $APP_DIR/scout.env (OPENAI_API_KEY, SCOUT_PASSWORD), затем перезапустите: systemctl restart scout"
fi

chown -R scout:scout "$APP_DIR"

echo "==> systemd-сервис"
cp "$APP_DIR/deploy/scout.service" /etc/systemd/system/scout.service
systemctl daemon-reload
systemctl enable --now scout

echo "==> nginx"
if [ ! -f /etc/nginx/sites-enabled/scout ]; then
    cp "$APP_DIR/deploy/nginx.conf.example" /etc/nginx/sites-available/scout
    ln -sf /etc/nginx/sites-available/scout /etc/nginx/sites-enabled/scout
    echo "!!! Впишите домен/IP в /etc/nginx/sites-available/scout"
fi
nginx -t && systemctl reload nginx || true

echo
echo "Готово. Дальше:"
echo "  1) nano $APP_DIR/scout.env   — впишите OPENAI_API_KEY и SCOUT_PASSWORD"
echo "  2) systemctl restart scout"
echo "  3) журнал:  journalctl -u scout -f"
echo "  4) откройте http://IP_СЕРВЕРА  (логин scout / ваш пароль)"
