"""
server.py — тонкий Flask-бэкенд для табличного (Clay-style) интерфейса AI Web Scout.

Заменяет Streamlit-фронт (app.py). Сам движок поиска НЕ меняется — каждый запуск
столбца дёргает run_pipeline() из pipeline.py, который переиспользует существующие
keywords → scrapy → LLM-воркеры.

Состояние держится в памяти процесса (без БД — «без надстроек»):
  STATE = { domains: [...], columns: [...], settings: {...} }

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

app = Flask(__name__, static_folder=None)

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# Палитра для аватарок доменов (совпадает с фронтом)
FAVI_COLORS = ["#0D9488", "#6366F1", "#EA580C", "#DB2777", "#0891B2",
               "#7C3AED", "#059669", "#D97706", "#2563EB", "#DC2626"]

# ------------------------------------------------------------------ STATE ---
STATE = {
    "domains": [],   # [{id, domain, name, color}]
    "columns": [],   # [{id, name, prompt, model, type, status, cells:{domId:{status,value,sourceUrl}}}]
    "settings": {"api_key": os.environ.get("OPENAI_API_KEY", ""),
                 "default_model": "gpt-4o-mini"},
}
RUN_LOCK = threading.Lock()   # синхронные прогоны: один запуск за раз


def pretty_name(domain: str) -> str:
    base = domain.split(".")[0].replace("-", " ").replace("_", " ")
    return " ".join(w.capitalize() for w in base.split() if w) or domain


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def public_state():
    """Состояние для фронта (ключ API не отдаём, только флаг наличия)."""
    s = STATE["settings"]
    return {
        "domains": STATE["domains"],
        "columns": STATE["columns"],
        "settings": {"has_key": bool(s["api_key"]), "default_model": s["default_model"]},
    }


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
        STATE["settings"]["api_key"] = (data["api_key"] or "").strip()
    if "default_model" in data:
        STATE["settings"]["default_model"] = data["default_model"]
    return jsonify(public_state())


@app.post("/api/domains")
def add_domains():
    data = request.get_json(force=True) or {}
    raw = data.get("text", "")
    incoming = []
    for token in raw.replace(",", "\n").splitlines():
        d = token.strip().lower()
        d = d.replace("https://", "").replace("http://", "").rstrip("/")
        if d:
            incoming.append(d)

    existing = {d["domain"] for d in STATE["domains"]}
    added = 0
    for dn in incoming:
        if dn in existing:
            continue
        existing.add(dn)
        dom = {
            "id": new_id("dom"),
            "domain": dn,
            "name": pretty_name(dn),
            "color": FAVI_COLORS[len(STATE["domains"]) % len(FAVI_COLORS)],
        }
        STATE["domains"].append(dom)
        # новый домен — пустые ячейки во всех столбцах
        for col in STATE["columns"]:
            col["cells"][dom["id"]] = {"status": "empty"}
        added += 1

    return jsonify({"added": added, **public_state()})


@app.delete("/api/domains/<dom_id>")
def delete_domain(dom_id):
    STATE["domains"] = [d for d in STATE["domains"] if d["id"] != dom_id]
    for col in STATE["columns"]:
        col["cells"].pop(dom_id, None)
    return jsonify(public_state())


@app.post("/api/columns")
def add_column():
    data = request.get_json(force=True) or {}
    col = {
        "id": new_id("col"),
        "name": (data.get("name") or "Новый столбец").strip(),
        "prompt": (data.get("prompt") or "").strip(),
        "model": data.get("model") or STATE["settings"]["default_model"],
        "type": data.get("type") or "ai",
        "status": "idle",
        "cells": {d["id"]: {"status": "empty"} for d in STATE["domains"]},
    }
    STATE["columns"].append(col)
    return jsonify({"column_id": col["id"], **public_state()})


@app.patch("/api/columns/<col_id>")
def edit_column(col_id):
    col = next((c for c in STATE["columns"] if c["id"] == col_id), None)
    if not col:
        return jsonify({"error": "column not found"}), 404
    data = request.get_json(force=True) or {}
    for field in ("name", "prompt", "model", "type"):
        if field in data:
            col[field] = data[field]
    return jsonify(public_state())


@app.delete("/api/columns/<col_id>")
def delete_column(col_id):
    STATE["columns"] = [c for c in STATE["columns"] if c["id"] != col_id]
    return jsonify(public_state())


def _run_columns(columns):
    """Синхронно прогоняет переданные столбцы через реальный движок."""
    api_key = STATE["settings"]["api_key"]
    if not api_key:
        return {"error": "no_api_key"}
    domains = [d["domain"] for d in STATE["domains"]]
    if not domains:
        return {"error": "no_domains"}

    # Ленивый импорт: сервер поднимается даже без установленных scrapy/openai
    try:
        from pipeline import run_pipeline
    except Exception as exc:  # noqa: BLE001
        return {"error": "pipeline_import", "detail": str(exc)}

    dom_by_name = {d["domain"]: d["id"] for d in STATE["domains"]}

    with RUN_LOCK:
        for col in columns:
            col["status"] = "running"
            try:
                results = run_pipeline(domains, col["prompt"], api_key, model=col["model"])
            except Exception as exc:  # noqa: BLE001
                col["status"] = "error"
                return {"error": "pipeline_failed", "detail": str(exc)}

            for dom_name, res in results.items():
                dom_id = dom_by_name.get(dom_name)
                if not dom_id:
                    continue
                if res.get("result"):
                    col["cells"][dom_id] = {
                        "status": "found",
                        "value": res["result"],
                        "sourceUrl": res.get("source_url"),
                    }
                else:
                    col["cells"][dom_id] = {"status": "notfound"}
            col["status"] = "done"
    return None


@app.post("/api/columns/<col_id>/run")
def run_column(col_id):
    col = next((c for c in STATE["columns"] if c["id"] == col_id), None)
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
    cols = [c for c in STATE["columns"] if c["prompt"]]
    if not cols:
        return jsonify({"error": "no_runnable_columns"}), 400
    err = _run_columns(cols)
    if err:
        return jsonify(err), 400
    return jsonify(public_state())


@app.get("/api/export.csv")
def export_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    headers = (["site"]
               + [c["name"] for c in STATE["columns"]]
               + [f'{c["name"]} — source_url' for c in STATE["columns"]])
    w.writerow(headers)
    for d in STATE["domains"]:
        vals, srcs = [], []
        for c in STATE["columns"]:
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
