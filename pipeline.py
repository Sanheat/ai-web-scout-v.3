"""
pipeline.py — переиспользуемая обёртка над существующим движком AI Web Scout.

Логика поиска данных НЕ меняется: это та же трёхстадийная схема, что и в app.py
(Streamlit), просто оформленная как вызываемая функция, чтобы её мог дёргать
тонкий Flask-бэкенд (server.py) по одному столбцу за раз.

  Stage 1 — get_keywords_from_query()  (llm_validator.py)
  Stage 2 — scrapy crawl site_spider   (scraper/spiders/site_spider.py)
  Stage 3 — process_site() в пуле       (run_llm_workers.py)

Состояние не хранится: функция синхронно возвращает результат по каждому домену.
"""

import os
import sys
import shutil
import tempfile
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional

import pandas as pd

from llm_validator import get_keywords_from_query
from run_llm_workers import load_candidates, process_site

# Те же лимиты, что и в текущем сервисе (app.py / run_llm_workers.py)
CHUNK_SIZE = 50            # доменов на один экземпляр краулера
MAX_PAGES_PER_SITE = 2     # страниц на домен для LLM-обработки
MAX_WORKERS = 4            # параллельных LLM-воркеров

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_pipeline(
    domains: List[str],
    query: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    progress: Optional[Callable[[str, Optional[object]], None]] = None,
    on_result: Optional[Callable[[str, Dict[str, Optional[str]]], None]] = None,
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Прогоняет список доменов через пайплайн под один запрос (один столбец Clay).

    Возвращает словарь: { домен: {"result": str|None, "source_url": str|None} }
    для ВСЕХ переданных доменов (ненайденные → None).

    progress(stage, payload) — необязательный колбэк для логов:
      stage="keywords" payload=[ключевые слова]
      stage="crawl"    payload=None
      stage="llm"      payload=None

    on_result(domain, {"result","source_url"}) — необязательный колбэк, вызывается
    по мере готовности КАЖДОГО домена. Позволяет сохранять прогресс инкрементально,
    чтобы падение/перезапуск посреди прогона не терял уже найденное.
    """
    domains = [d.strip() for d in domains if d and d.strip()]
    if not domains:
        return {}

    # --- Stage 1: ключевые слова -------------------------------------------
    keywords = get_keywords_from_query(query, api_key)
    keywords_str = ",".join(keywords)
    if progress:
        progress("keywords", keywords)

    workdir = tempfile.mkdtemp(prefix="scout_run_")
    candidate_files: List[str] = []
    try:
        # --- Stage 2: параллельный краулинг (шардинг по доменам) ------------
        chunks = [domains[i:i + CHUNK_SIZE] for i in range(0, len(domains), CHUNK_SIZE)]
        procs = []
        for idx, chunk in enumerate(chunks):
            chunk_file = os.path.join(workdir, f"sites_chunk_{idx}.csv")
            pd.DataFrame(chunk, columns=["site"]).to_csv(chunk_file, index=False)

            out_file = os.path.join(workdir, f"pages_part_{idx}.jl")
            candidate_files.append(out_file)

            cmd = [
                "scrapy", "crawl", "site_spider",
                "-a", f"sites_file={chunk_file}",
                "-a", f"user_query={query}",
                "-a", f"keywords={keywords_str}",
                "-o", out_file,
            ]
            procs.append(subprocess.Popen(
                cmd, cwd=PROJECT_DIR,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ))

        if progress:
            progress("crawl", None)

        for p in procs:
            p.communicate()  # ждём завершения всех краулеров

        # --- Stage 3: LLM-извлечение в пуле воркеров -----------------------
        if progress:
            progress("llm", None)

        candidates = load_candidates(candidate_files)

        by_site: Dict[str, list] = defaultdict(list)
        for rec in candidates:
            site = rec.get("site")
            if site:
                by_site[site].append(rec)

        found: Dict[str, Dict[str, Optional[str]]] = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {
                ex.submit(process_site, site, recs, api_key, MAX_PAGES_PER_SITE, model): site
                for site, recs in by_site.items()
            }
            for fut in as_completed(futures):
                site = futures[fut]
                try:
                    r = fut.result()
                except Exception:
                    r = {"site": site, "result": None, "source_url": None}
                cell = {"result": r.get("result"), "source_url": r.get("source_url")}
                found[site] = cell
                if on_result:
                    try:
                        on_result(site, cell)   # инкрементальное сохранение
                    except Exception:
                        pass

        # Домены без кандидатов (краулер ничего не принёс) — тоже отдаём (как не найдено)
        out: Dict[str, Dict[str, Optional[str]]] = {}
        for d in domains:
            cell = found.get(d, {"result": None, "source_url": None})
            out[d] = cell
            if d not in found and on_result:
                try:
                    on_result(d, cell)
                except Exception:
                    pass
        return out
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
