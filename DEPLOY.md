# Деплой AI Web Scout онлайн

Чтобы скинуть человеку рабочую ссылку, сервису нужен **постоянно работающий
сервер** (не serverless): краулинг идёт долго (минуты), а состояние хранится в
SQLite на диске. Ниже — рабочие варианты.

> **Пароль на вход.** На публичном хостинге обязательно задайте переменную
> `SCOUT_PASSWORD`. Тогда при заходе по ссылке браузер спросит логин/пароль
> (логин по умолчанию `scout`, меняется через `SCOUT_USER`). Без этой
> переменной доступ открыт — годится только локально.

---

## ⭐ Рекомендуется: Render (один клик, как Vercel по простоте)

1. Залейте репозиторий на GitHub (уже сделано: ветка `main`).
2. Зайдите на https://render.com → **New → Blueprint** → подключите репозиторий.
   Render прочитает `render.yaml` и создаст web-сервис из `Dockerfile`.
3. В разделе **Environment** задайте секреты:
   - `OPENAI_API_KEY` = ваш ключ OpenAI
   - `SCOUT_PASSWORD` = простой пароль на вход (например, `demo2026`)
4. **Create** → дождитесь сборки. Получите ссылку вида
   `https://ai-web-scout.onrender.com` — её и отправляете человеку (вместе с
   паролем).

**Бесплатный план:** сервис «засыпает» при простое (первый заход ~30 сек) и
файловая система эфемерная — `scout.db` сбрасывается при редеплое. Для
постоянного хранения переключите план на `starter` и раскомментируйте блок
`disk:` в `render.yaml` (БД будет в `/data/scout.db`).

---

## 🇷🇺 Российский VPS (always-on, не засыпает, не теряет работу)

Лучший вариант, если важно, чтобы сервис работал постоянно и переживал сбои.
На VPS он крутится 24/7, а `systemd` с `Restart=always` сам поднимает его после
любого падения — выполненная работа уже сохранена в `scout.db` (результат пишется
по каждому домену сразу), поэтому **ничего не обнуляется**.

**Провайдеры** (хватит тарифа ~1–2 vCPU / 2 ГБ RAM, примерно 200–500 ₽/мес):

| Провайдер | Заметки |
|---|---|
| **Timeweb Cloud** (timeweb.cloud) | Просто, быстро, дёшево — хороший выбор по умолчанию |
| **Beget** (beget.com) | Дешёвый VPS, простая панель |
| **Selectel** (selectel.ru) | Надёжный, чуть дороже, больше возможностей |
| **RuVDS / VDSina / Aéza** | Бюджетные VPS |
| **Yandex Cloud / VK Cloud** | Enterprise, pay-as-you-go, сложнее в настройке |

### Установка (Ubuntu 22.04/24.04)

```bash
# на сервере под root:
apt-get update && apt-get install -y git
git clone https://github.com/Sanheat/ai-web-scout-v.3.git /opt/ai-web-scout
bash /opt/ai-web-scout/deploy/setup-vps.sh

# затем вписать секреты и перезапустить:
nano /opt/ai-web-scout/scout.env     # OPENAI_API_KEY, SCOUT_PASSWORD
systemctl restart scout
journalctl -u scout -f               # смотреть лог
```

Скрипт ставит зависимости, создаёт venv, заводит `systemd`-сервис (gunicorn,
1 воркер, авто-рестарт) и nginx-прокси. Готовые конфиги — в папке `deploy/`
(`scout.service`, `scout.env.example`, `nginx.conf.example`).

Открой `http://IP_СЕРВЕРА` (логин `scout` / твой пароль). Для домена и HTTPS:
впиши домен в `/etc/nginx/sites-available/scout` и выполни
`certbot --nginx -d твой-домен.ru`.

> **⚠️ OpenAI из России.** OpenAI блокирует запросы с российских IP — движок
> (он ходит в `api.openai.com`) может получать ошибку региона. Варианты:
> прокси для исходящих запросов к OpenAI, либо перевод движка на доступную в РФ
> модель (YandexGPT, GigaChat, или OpenAI-совместимый шлюз через `base_url`).
> Это отдельная небольшая доработка — скажи, если нужно.

---

## 🌍 Зарубежный бесплатный / почти бесплатный хостинг

Плюс зарубежного хостинга: запросы к OpenAI идут с не-российского IP, поэтому
движок работает без прокси. Для нашего приложения нужна **настоящая виртуалка**
(не serverless) — тогда нет лимита на длину запроса и есть постоянный диск.

| Вариант | Цена | Засыпает? | Заметки |
|---|---|---|---|
| **Oracle Cloud — Always Free** ⭐ | Бесплатно навсегда | Нет | Реальная VM (ARM Ampere до 4 vCPU/24 ГБ). Ставится нашим `deploy/`-китом. Лучший бесплатный always-on. Нужна карта для регистрации (без списания) |
| **Google Cloud — Always Free** | Бесплатно (e2-micro, отд. регионы US) | Нет | Маленькая VM (1 ГБ), но для лёгкой нагрузки хватает. Нужна карта |
| **AWS Free Tier** | Бесплатно 12 мес (t3.micro) | Нет | Только первый год, потом платно |
| **Fly.io** | ~$2–3/мес (есть кредиты) | Нет (min 1 machine) | Использует наш `Dockerfile`, постоянный том. Очень дёшево |
| **Render Free / Vercel** | Бесплатно | **Да / serverless** | Засыпает, эфемерный диск, таймауты — для долгого краулинга **не годится** |

### Oracle Cloud Always Free — пошагово ⭐

**Что получится:** постоянно работающий сервис по адресу `http://ВАШ_IP`
(или своему домену), под паролем, OpenAI доступен, вся работа в `scout.db` и
переживает перезапуски. Стоимость — 0 ₽.

**1. Регистрация.** https://cloud.oracle.com → *Start for free*. Нужна
банковская карта (только верификация, без списания) и телефон. Домашний регион
выбирай поближе (например, Frankfurt или Amsterdam) — потом не меняется.

**2. Создать VM.** Menu → *Compute* → *Instances* → *Create instance*:
- **Image:** Canonical Ubuntu 22.04.
- **Shape:** *Ampere* (ARM, Always Free) — `VM.Standard.A1.Flex`, например
  2 OCPU / 12 ГБ (в лимит Always Free входит до 4 OCPU / 24 ГБ суммарно).
  Если пишет *Out of capacity* — попробуй позже, другой Availability Domain,
  или возьми Always Free AMD `VM.Standard.E2.1.Micro` (слабее, но хватает).
- **SSH:** загрузи свой публичный ключ (или сгенерируй и скачай приватный).
- Создай и запомни **Public IP**.

**3. Открыть порты — главный подводный камень Oracle (два фаервола!).**
- *Security List:* Networking → VCN → Subnet → Security List → *Add Ingress
  Rules*: Source `0.0.0.0/0`, TCP порт `80` (и `443` для HTTPS).
- *На самой VM* (Ubuntu-образ Oracle по умолчанию режет входящие через iptables):
  ```bash
  sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
  sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
  sudo apt-get install -y iptables-persistent && sudo netfilter-persistent save
  ```

**4. Установить сервис** (по SSH):
```bash
ssh ubuntu@ВАШ_IP
sudo apt-get update && sudo apt-get install -y git
sudo git clone https://github.com/Sanheat/ai-web-scout-v.3.git /opt/ai-web-scout
sudo bash /opt/ai-web-scout/deploy/setup-vps.sh
sudo nano /opt/ai-web-scout/scout.env      # OPENAI_API_KEY, SCOUT_PASSWORD
sudo systemctl restart scout
```

**5. Указать IP/домен в nginx:**
```bash
sudo nano /etc/nginx/sites-available/scout  # server_name = ВАШ_IP или домен
sudo nginx -t && sudo systemctl reload nginx
```

**6. Открыть** `http://ВАШ_IP` → логин `scout` / твой пароль. Готово.

**7. (Опционально) домен + HTTPS:** направь A-запись домена на IP, затем
`sudo apt-get install -y certbot python3-certbot-nginx && sudo certbot --nginx -d твой-домен`.

> Always Free VM не останавливается сама. Повторный запуск `setup-vps.sh`
> безопасен — он сделает `git pull` и обновит сервис.

### Open-source решения (self-hosted PaaS)

Если хочется деплой «как на Vercel» (Git push + UI), но на своём сервере —
поставь на ту же бесплатную VM один из open-source PaaS:

- **Coolify** (coolify.io) — самый популярный, веб-UI, деплой из Git/Docker.
- **Dokku** (dokku.com) — лёгкий мини-Heroku, `git push` → деплой.
- **CapRover** (caprover.com) — Docker-PaaS с веб-панелью.

Они сами по себе бесплатны, но им нужен сервер (та же Oracle Free VM). Для
одного нашего приложения проще обойтись готовым `systemd`-китом из `deploy/`,
но если планируешь несколько сервисов — Coolify удобнее.

---

## Альтернатива: Railway / Fly.io

Оба видят `Dockerfile` автоматически.

- **Railway:** New Project → Deploy from GitHub repo → добавьте переменные
  `OPENAI_API_KEY`, `SCOUT_PASSWORD`. Для постоянной БД добавьте Volume на
  `/data`.
- **Fly.io:** `fly launch` (подхватит Dockerfile) → `fly volumes create scout_data`
  → смонтируйте на `/data` → `fly secrets set OPENAI_API_KEY=... SCOUT_PASSWORD=...`.

---

## Быстрый туннель (показать прямо сейчас, без хостинга)

Ссылка живёт, пока запущен ваш компьютер. Бесплатно, за минуту.

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
export SCOUT_PASSWORD=demo2026
python server.py            # локально на :8000

# в другом терминале — публичный https-адрес:
npx cloudflared tunnel --url http://localhost:8000
# или: ngrok http 8000
```

---

## Про Vercel (важно прочитать)

**Vercel не подходит для бэкенда этого сервиса.** Vercel — это serverless
(короткоживущие функции), а у нас:

| Требование сервиса | Ограничение Vercel |
|---|---|
| Краулинг идёт минутами | Лимит выполнения функции: Hobby 60 сек, Pro до 300 сек → прогон **отвалится по таймауту** |
| Состояние в SQLite на диске | На Vercel нет постоянного диска (только `/tmp`, эфемерный) → **данные не сохранятся** |
| `scrapy` как подпроцесс, Twisted | Нестабильно в serverless-функции |
| Один процесс (блокировка запусков, ключ в памяти) | Каждый запрос — новый изолированный инстанс |

Поэтому «просто задеплоить на Vercel» приведёт к нерабочему краулингу и потере
данных. Есть два честных пути, если Vercel принципиально нужен:

1. **Гибрид (если хочется именно Vercel):** статический фронт (`web/index.html`)
   — на Vercel, а бэкенд (`server.py`) — на Render/Railway/Fly. Потребуется
   мелкая доработка: вынести адрес API в конфиг фронта и включить CORS на
   бэкенде. Готов сделать — скажите.
2. **Проще:** разместить всё на Render (см. выше) — одна ссылка, всё работает,
   по простоте не сложнее Vercel.

Рекомендация: **вариант с Render.** Если нужен именно гибрид с Vercel —
подготовлю CORS и конфиг фронта отдельным шагом.
