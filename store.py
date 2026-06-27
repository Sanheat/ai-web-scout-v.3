"""
store.py — постоянное хранение состояния AI Web Scout в SQLite.

SQLite — единственный источник правды для доменов, столбцов и ячеек, чтобы
состояние переживало перезапуск сервера. API-ключ здесь НЕ хранится (секрет
остаётся в памяти процесса / env) — персистится только default_model.

Каждая операция открывает короткое соединение под одним общим RLock, чтобы быть
потокобезопасной при Flask threaded=True (sqlite3-соединения не шарятся между
потоками).
"""

import os
import sqlite3
import threading

DB_PATH = os.environ.get(
    "SCOUT_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "scout.db"),
)

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS domains (
    id     TEXT PRIMARY KEY,
    domain TEXT UNIQUE NOT NULL,
    name   TEXT,
    color  TEXT
);
CREATE TABLE IF NOT EXISTS columns (
    id     TEXT PRIMARY KEY,
    name   TEXT,
    prompt TEXT,
    model  TEXT,
    type   TEXT,
    status TEXT
);
CREATE TABLE IF NOT EXISTS cells (
    column_id  TEXT NOT NULL REFERENCES columns(id)  ON DELETE CASCADE,
    domain_id  TEXT NOT NULL REFERENCES domains(id)  ON DELETE CASCADE,
    status     TEXT,
    value      TEXT,
    source_url TEXT,
    PRIMARY KEY (column_id, domain_id)
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init():
    with _lock, _conn() as c:
        c.executescript(SCHEMA)


# --------------------------------------------------------------- reads ----
def load_state():
    """Полное состояние для фронта (без api_key)."""
    with _lock, _conn() as c:
        domains = [dict(r) for r in c.execute(
            "SELECT id, domain, name, color FROM domains ORDER BY rowid")]

        columns = []
        for r in c.execute(
                "SELECT id, name, prompt, model, type, status FROM columns ORDER BY rowid"):
            col = dict(r)
            cells = {}
            for cr in c.execute(
                    "SELECT domain_id, status, value, source_url FROM cells WHERE column_id=?",
                    (col["id"],)):
                cell = {"status": cr["status"] or "empty"}
                if cr["value"] is not None:
                    cell["value"] = cr["value"]
                if cr["source_url"] is not None:
                    cell["sourceUrl"] = cr["source_url"]
                cells[cr["domain_id"]] = cell
            col["cells"] = cells
            columns.append(col)

        row = c.execute("SELECT value FROM settings WHERE key='default_model'").fetchone()
        default_model = row["value"] if row else "gpt-4o-mini"

        return {"domains": domains, "columns": columns,
                "settings": {"default_model": default_model}}


def domain_names():
    with _lock, _conn() as c:
        return {r["domain"] for r in c.execute("SELECT domain FROM domains")}


def count_domains():
    with _lock, _conn() as c:
        return c.execute("SELECT COUNT(*) AS n FROM domains").fetchone()["n"]


def get_column(col_id):
    with _lock, _conn() as c:
        r = c.execute(
            "SELECT id, name, prompt, model, type, status FROM columns WHERE id=?",
            (col_id,)).fetchone()
        return dict(r) if r else None


def list_columns():
    with _lock, _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, name, prompt, model, type, status FROM columns ORDER BY rowid")]


def domain_id_by_name():
    with _lock, _conn() as c:
        return {r["domain"]: r["id"] for r in c.execute("SELECT id, domain FROM domains")}


# -------------------------------------------------------------- writes ----
def add_domain(dom):
    """Вставляет домен и пустые ячейки во все столбцы. True если добавлен."""
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO domains(id, domain, name, color) VALUES(?,?,?,?)",
            (dom["id"], dom["domain"], dom["name"], dom["color"]))
        if cur.rowcount != 1:
            return False
        for r in c.execute("SELECT id FROM columns"):
            c.execute(
                "INSERT OR IGNORE INTO cells(column_id, domain_id, status) VALUES(?,?,'empty')",
                (r["id"], dom["id"]))
        return True


def delete_domain(dom_id):
    with _lock, _conn() as c:
        c.execute("DELETE FROM domains WHERE id=?", (dom_id,))  # cells cascade


def add_column(col):
    """Вставляет столбец и пустые ячейки по всем доменам."""
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO columns(id, name, prompt, model, type, status) VALUES(?,?,?,?,?,?)",
            (col["id"], col["name"], col["prompt"], col["model"], col["type"], col["status"]))
        for r in c.execute("SELECT id FROM domains"):
            c.execute(
                "INSERT OR IGNORE INTO cells(column_id, domain_id, status) VALUES(?,?,'empty')",
                (col["id"], r["id"]))


def update_column(col_id, fields):
    allowed = {"name", "prompt", "model", "type", "status"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    cols = ", ".join(f"{k}=?" for k in sets)
    with _lock, _conn() as c:
        c.execute(f"UPDATE columns SET {cols} WHERE id=?", (*sets.values(), col_id))


def delete_column(col_id):
    with _lock, _conn() as c:
        c.execute("DELETE FROM columns WHERE id=?", (col_id,))  # cells cascade


def upsert_cell(column_id, domain_id, cell):
    with _lock, _conn() as c:
        c.execute(
            """INSERT INTO cells(column_id, domain_id, status, value, source_url)
                 VALUES(?,?,?,?,?)
               ON CONFLICT(column_id, domain_id)
                 DO UPDATE SET status=excluded.status,
                               value=excluded.value,
                               source_url=excluded.source_url""",
            (column_id, domain_id, cell.get("status", "empty"),
             cell.get("value"), cell.get("sourceUrl")))


def reset_running_columns():
    """При старте сервера сбрасываем 'зависшие' running-столбцы в idle.

    Если процесс упал/перезапустился посреди прогона, статус running остался бы
    навсегда. Уже сохранённые ячейки (found/notfound) при этом сохраняются.
    """
    with _lock, _conn() as c:
        c.execute("UPDATE columns SET status='idle' WHERE status='running'")


def get_setting(key, default=None):
    with _lock, _conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default


def set_setting(key, value):
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO settings(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value))
