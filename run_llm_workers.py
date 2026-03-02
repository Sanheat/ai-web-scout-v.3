import argparse
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Any

from llm_validator import validate_with_llm


def load_candidates(input_files: List[str]) -> List[Dict[str, Any]]:
    """Загружает кандидатов из одного или нескольких JSON Lines файлов, созданных Scrapy (формат .jl)."""
    candidates: List[Dict[str, Any]] = []

    for file_path in input_files:
        path = Path(file_path)
        if not path.exists():
            continue

        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    candidates.append(record)
                except json.JSONDecodeError:
                    # Пропускаем битые строки, но не падаем
                    continue

    return candidates


def process_site(site: str, records: List[Dict[str, Any]], api_key: str, max_pages_per_site: int = 2) -> Dict[str, Any]:
    """
    Обрабатывает всех кандидатов для одного домена, вызывая LLM последовательно,
    пока не найдется уверенный результат или не будет исчерпан лимит страниц.
    """
    used = 0

    for record in records:
        if used >= max_pages_per_site:
            break

        html = record.get("html", "")
        url = record.get("page_url") or record.get("url")
        user_query = record.get("user_query", "")

        if not html or not url or not user_query:
            continue

        used += 1

        extracted = validate_with_llm(
            html_content=html,
            url=url,
            user_query=user_query,
            api_key=api_key,
        )

        if extracted:
            return {
                "site": site,
                "result": extracted,
                "source_url": url,
            }

    # Ничего не найдено
    return {
        "site": site,
        "result": None,
        "source_url": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM workers over crawled page candidates.")
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="JSON Lines files (.jl) с кандидатами страниц от Scrapy (можно несколько).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Путь к CSV-файлу с финальными результатами (site, result, source_url).",
    )
    parser.add_argument(
        "--api_key",
        required=True,
        help="OpenAI API key для LLM-запросов.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        dest="max_workers",
        help="Максимальное количество параллельных воркеров (по сайтам).",
    )
    parser.add_argument(
        "--max-pages-per-site",
        type=int,
        default=2,
        dest="max_pages_per_site",
        help="Максимальное количество страниц на один сайт для LLM-обработки.",
    )

    args = parser.parse_args()

    candidates = load_candidates(args.inputs)
    if not candidates:
        # Ничего не crawled — выходим, оставляя фронтэнду обработку пустых результатов
        Path(args.output).write_text("", encoding="utf-8")
        return

    # Группируем кандидатов по домену
    by_site: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in candidates:
        site = record.get("site")
        if not site:
            continue
        by_site[site].append(record)

    results: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_site = {
            executor.submit(process_site, site, records, args.api_key, args.max_pages_per_site): site
            for site, records in by_site.items()
        }

        for future in as_completed(future_to_site):
            site = future_to_site[future]
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception as exc:  # noqa: BLE001
                # В случае аварии по сайту просто пропускаем его, фронтенд покажет "Не найдено"
                results.append(
                    {
                        "site": site,
                        "result": None,
                        "source_url": None,
                    }
                )

    # Записываем результаты в CSV, который читает Streamlit
    import pandas as pd  # Локальный импорт, чтобы не тянуть pandas, если скрипт используется отдельно

    df = pd.DataFrame(results)
    df.to_csv(args.output, index=False)


if __name__ == "__main__":
    main()

