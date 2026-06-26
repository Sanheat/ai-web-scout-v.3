"""
server.py — тонкий Flask-бэкенд для табличного (Clay-style) интерфейса AI Web Scout.

Заменяет Streamlit-фронт (app.py). Сам движок поиска НЕ меняется — каждый запуск
столбца дёргает run_pipeline() из pipeline.py (keywords → scrapy → LLM-воркеры).

Состояние (домены, столбцы, ячейки) хранится в SQLite через store.py и переживает
перезапуск сервера. API-ключ на диск не пишется: живёт в памяти процесса / env.

Запуск:
    pip install -r requirements.txt
    export OPENAI_API_KEY=sk-...        # необязательно, можно ввести в UI
    python server.py                    # → http://127.0.0.1:8000
"""

import os
import io
import csv
import uuid
import threading

from flask import Flask, request, jsonify, send_from_directory, Response

import store

app = Flask(__name__, static_folder=None)

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

FAVI_COLORS = ["#0D9488", "#6366F1", "#EA580C", "#DB2777", "#0891B2",
               "#7C3AED", "#059669", "#D97706", "#2563EB", "#DC2626"]

# Секрет — только в памяти, не в БД
RUNTIME = {"api_key": os.environ.get("OPENAI_API_KEY", "")}
RUN_LOCK = threading.Lock()   # синхронные прогоны: один запуск за раз

store.init()


def pretty_name(domain: str) -> str:
    base = domain.split(".")[0].replace("-", " ").replace("_", " ")
    return " ".join(w.capitalize() for w in base.split() if w) or domain


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def public_state():
    state = store.load_state()
    state["settings"] = {
        "has_key": bool(RUNTIME["api_key"]),
        "default_model": state["settings"]["default_model"],
    }
    return state


# --------------------------------------------------------------- STATIC ----
@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(WEB_DIR, path)


# ------------------------------------------------------------------ API ----
@app.get("/api/state")
def get_state():
    return jsonify(public_state())


@app.post("/api/settings")
def set_settings():
    data = request.get_json(force=True) or {}
    if "api_key" in data:
        RUNTIME["api_key"] = (data["api_key"] or "").strip()
    if "default_model" in data:
        store.set_setting("default_model", data["default_model"])
    return jsonify(public_state())


@app.post("/api/domains")
def add_domains():
    data = request.get_json(force=True) or {}
    raw = data.get("text", "")
    incoming = []
    for token in raw.replace(",", "\n").splitlines():
        d = token.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
        if d:
            incoming.append(d)

    existing = store.domain_names()
    n = store.count_domains()
    added = 0
    seen = set()
    for dn in incoming:
        if dn in existing or dn in seen:
            continue
        seen.add(dn)
        dom = {
            "id": new_id("dom"),
            "domain": dn,
            "name": pretty_name(dn),
            "color": FAVI_COLORS[n % len(FAVI_COLORS)],
        }
        if store.add_domain(dom):
            n += 1
            added += 1

    return jsonify({"added": added, **public_state()})


@app.delete("/api/domains/<dom_id>")
def delete_domain(dom_id):
    store.delete_domain(dom_id)
    return jsonify(public_state())


@app.post("/api/columns")
def add_column():
    data = request.get_json(force=True) or {}
    col = {
        "id": new_id("col"),
        "name": (data.get("name") or "Новый столбец").strip(),
        "prompt": (data.get("prompt") or "").strip(),
        "model": data.get("model") or store.get_setting("default_model", "gpt-4o-mini"),
        "type": data.get("type") or "ai",
        "status": "idle",
    }
    store.add_column(col)
    return jsonify({"column_id": col["id"], **public_state()})


@app.patch("/api/columns/<col_id>")
def edit_column(col_id):
    if not store.get_column(col_id):
        return jsonify({"error": "column not found"}), 404
    data = request.get_json(force=True) or {}
    store.update_column(col_id, {k: data[k] for k in ("name", "prompt", "model", "type") if k in data})
    return jsonify(public_state())


@app.delete("/api/columns/<col_id>")
def delete_column(col_id):
    store.delete_column(col_id)
    return jsonify(public_state())


def _run_columns(columns):
    """Синхронно прогоняет переданные столбцы через реальный движок."""
    api_key = RUNTIME["api_key"]
    if not api_key:
        return {"error": "no_api_key"}

    state = store.load_state()
    domains = [d["domain"] for d in state["domains"]]
    if not domains:
        return {"error": "no_domains"}

    # Ленивый импорт: сервер поднимается даже без установленных scrapy/openai
    try:
        from pipeline import run_pipeline
    except Exception as exc:  # noqa: BLE001
        return {"error": "pipeline_import", "detail": str(exc)}

    dom_by_name = store.domain_id_by_name()

    with RUN_LOCK:
        for col in columns:
            store.update_column(col["id"], {"status": "running"})
            try:
                results = run_pipeline(domains, col["prompt"], api_key, model=col["model"])
            except Exception as exc:  # noqa: BLE001
                store.update_column(col["id"], {"status": "error"})
                return {"error": "pipeline_failed", "detail": str(exc)}

            for dom_name, res in results.items():
                dom_id = dom_by_name.get(dom_name)
                if not dom_id:
                    continue
                if res.get("result"):
                    store.upsert_cell(col["id"], dom_id, {
                        "status": "found",
                        "value": res["result"],
                        "sourceUrl": res.get("source_url"),
                    })
                else:
                    store.upsert_cell(col["id"], dom_id, {"status": "notfound"})
            store.update_column(col["id"], {"status": "done"})
    return None


@app.post("/api/columns/<col_id>/run")
def run_column(col_id):
    col = store.get_column(col_id)
    if not col:
        return jsonify({"error": "column not found"}), 404
    if not col["prompt"]:
        return jsonify({"error": "empty_prompt"}), 400
    err = _run_columns([col])
    if err:
        return jsonify(err), 400
    return jsonify(public_state())


@app.post("/api/run-all")
def run_all():
    cols = [c for c in store.list_columns() if c["prompt"]]
    if not cols:
        return jsonify({"error": "no_runnable_columns"}), 400
    err = _run_columns(cols)
    if err:
        return jsonify(err), 400
    return jsonify(public_state())


@app.get("/api/export.csv")
def export_csv():
    state = store.load_state()
    buf = io.StringIO()
    w = csv.writer(buf)
    headers = (["site"]
               + [c["name"] for c in state["columns"]]
               + [f'{c["name"]} — source_url' for c in state["columns"]])
    w.writerow(headers)
    for d in state["domains"]:
        vals, srcs = [], []
        for c in state["columns"]:
            cell = c["cells"].get(d["id"], {})
            if cell.get("status") == "found":
                vals.append(cell.get("value", ""))
                srcs.append(cell.get("sourceUrl", "") or "")
            elif cell.get("status") == "notfound":
                vals.append("❌ Не найдено")
                srcs.append("")
            else:
                vals.append("")
                srcs.append("")
        w.writerow([d["domain"]] + vals + srcs)

    return Response(
        "﻿" + buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=scout_results.csv"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
