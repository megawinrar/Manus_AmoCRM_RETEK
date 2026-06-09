#!/usr/bin/env python3
"""
RAG Search — Семантический поиск по индексированным тендерам.

Использует Yandex text-search-query для запросов и ChromaDB для поиска.
Возвращает релевантные фрагменты с указанием источников.

Использование:
    # Простой поиск
    python3 scripts/rag_search.py "какие условия поставки?"

    # Поиск по конкретному тендеру
    python3 scripts/rag_search.py "штрафы за просрочку" --tender-id "2109-2026-00743"

    # Поиск + ответ через YandexGPT
    python3 scripts/rag_search.py "можно ли предложить аналог?" --answer

    # JSON-вывод (для интеграции)
    python3 scripts/rag_search.py "НМЦ закупки" --json

    # Интерактивный режим
    python3 scripts/rag_search.py --interactive
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Optional

import requests

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

YANDEX_API_KEY = os.environ.get("YANDEX_GPT_API_KEY", "")
YANDEX_FOLDER_ID = os.environ.get("YANDEX_GPT_FOLDER_ID", "")
QUERY_MODEL = os.environ.get("YANDEX_EMBEDDING_QUERY_MODEL", "text-search-query/latest")
GPT_MODEL = os.environ.get("YANDEX_GPT_MODEL", "yandexgpt-lite/latest")
GPT_MODEL_STRONG = os.environ.get("YANDEX_GPT_MODEL_STRONG", "yandexgpt/latest")

CHROMA_DB_PATH = Path(__file__).parent.parent / "data" / "chroma_db"
EMBEDDING_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"
COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

TOP_K = 10  # Number of results to return (increased from 5)
SIMILARITY_THRESHOLD = 0.25  # Minimum cosine similarity (slightly relaxed)

# ═══════════════════════════════════════════════════════════════════════════
# QUERY EXPANSION — расшифровка аббревиатур и синонимов
# ═══════════════════════════════════════════════════════════════════════════

ABBREVIATION_MAP = {
    "гисп": "ГИСП реестр промышленной продукции gisp.gov.ru реестровая запись",
    "нмц": "начальная максимальная цена договора НМЦ сумма итого стоимость",
    "ндс": "налог на добавленную стоимость НДС с учётом без учёта",
    "тз": "техническое задание ТЗ требования спецификация",
    "кп": "коммерческое предложение КП расчёт себестоимость",
    "етпрф": "ЕТПРФ электронная торговая площадка etprf.ru",
    "ззк": "закрытый запрос котировок ЗЗК процедура закупка",
    "ззп": "закрытый запрос предложений ЗЗП процедура",
    "еис": "единая информационная система ЕИС zakupki.gov.ru",
    "обеспечение": "обеспечение заявки исполнения контракта банковская гарантия",
    "штраф": "штраф пеня неустойка ответственность просрочка нарушение",
    "эквивалент": "эквивалент аналог или эквивалент допускается замена",
    "поставка": "поставка срок поставки партия доставка отгрузка",
    "оплата": "оплата платёж аванс предоплата расчёт порядок оплаты",
    "фрезы": "фреза фрезы концевая фреза твердосплавная фреза инструмент",
    "развёртки": "развёртка развёртки reamers разворачивание",
    "граверы": "гравер граверы гравировальный инструмент",
}


def expand_query(query: str) -> str:
    """
    Expand query with synonyms and abbreviation definitions.
    
    Example: "ГИСП" → "ГИСП реестр промышленной продукции gisp.gov.ru реестровая запись"
    """
    query_lower = query.lower()
    expansions = []
    
    for abbr, expansion in ABBREVIATION_MAP.items():
        if abbr in query_lower:
            expansions.append(expansion)
    
    if expansions:
        expanded = query + " " + " ".join(expansions)
        return expanded[:8000]  # API limit
    
    return query


# ═══════════════════════════════════════════════════════════════════════════
# EMBEDDING (query model)
# ═══════════════════════════════════════════════════════════════════════════

def embed_query(text: str) -> Optional[List[float]]:
    """Get embedding for a search query using text-search-query model."""
    model_uri = f"emb://{YANDEX_FOLDER_ID}/{QUERY_MODEL}"
    
    try:
        resp = requests.post(
            EMBEDDING_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {YANDEX_API_KEY}",
                "x-folder-id": YANDEX_FOLDER_ID,
                "x-data-logging-enabled": "false",
            },
            json={
                "modelUri": model_uri,
                "text": text[:8000],  # Truncate if too long
            },
            timeout=30,
        )
        
        if resp.status_code == 200:
            return resp.json()["embedding"]
        else:
            print(f"  [ERROR] Query embedding API {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  [ERROR] Query embedding failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════════════════════

def search(
    query: str,
    tender_id: Optional[str] = None,
    top_k: int = TOP_K,
    collection_name: str = "tenders",
    use_expansion: bool = True,
) -> List[Dict]:
    """
    Semantic search over indexed tenders.
    
    Returns list of results with:
    - text: chunk text
    - score: cosine similarity (0-1, higher = more relevant)
    - source: {tender_id, filename, chunk_idx, start_char, end_char}
    """
    import chromadb
    
    # Query expansion — add synonyms/abbreviation definitions
    search_query = expand_query(query) if use_expansion else query
    
    # Get query embedding
    query_embedding = embed_query(search_query)
    if query_embedding is None:
        return []
    
    # Open ChromaDB
    if not CHROMA_DB_PATH.exists():
        print("[ERROR] ChromaDB not found. Run rag_indexer.py first.")
        return []
    
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    
    try:
        collection = client.get_collection(collection_name)
    except Exception:
        print(f"[ERROR] Collection '{collection_name}' not found.")
        return []
    
    # Build query params — fetch 3x top_k for keyword re-ranking headroom
    fetch_count = min(top_k * 3, 50)
    query_params = {
        "query_embeddings": [query_embedding],
        "n_results": fetch_count,
        "include": ["documents", "metadatas", "distances"],
    }
    
    # Filter by tender_id if specified
    if tender_id:
        query_params["where"] = {"tender_id": tender_id}
    
    # Search
    results = collection.query(**query_params)
    
    # Format results with keyword boost
    formatted = []
    
    # Extract keywords from original query for boosting
    query_keywords = set()
    for word in query.lower().split():
        if len(word) >= 3:  # Only meaningful words
            query_keywords.add(word)
    # Also add expanded abbreviation keywords
    for abbr, expansion in ABBREVIATION_MAP.items():
        if abbr in query.lower():
            for w in expansion.lower().split():
                if len(w) >= 4:
                    query_keywords.add(w)
    
    if results and results["ids"] and results["ids"][0]:
        for i, (doc, meta, distance) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )):
            # ChromaDB returns distance, convert to similarity
            # For cosine: similarity = 1 - distance
            similarity = 1 - distance
            
            if similarity < SIMILARITY_THRESHOLD:
                continue
            
            # Keyword boost: if chunk contains exact keywords from query
            doc_lower = doc.lower()
            keyword_hits = sum(1 for kw in query_keywords if kw in doc_lower)
            keyword_boost = min(keyword_hits * 0.03, 0.15)  # max +0.15 boost
            
            boosted_score = similarity + keyword_boost
            
            formatted.append({
                "rank": 0,  # will be re-assigned after sorting
                "text": doc,
                "score": round(boosted_score, 4),
                "keyword_hits": keyword_hits,
                "source": {
                    "tender_id": meta.get("tender_id", ""),
                    "tender_name": meta.get("tender_name", ""),
                    "filename": meta.get("filename", ""),
                    "chunk_idx": meta.get("chunk_idx", 0),
                    "start_char": meta.get("start_char", 0),
                    "end_char": meta.get("end_char", 0),
                },
            })
    
    # Re-sort by boosted score and assign ranks
    formatted.sort(key=lambda x: x["score"], reverse=True)
    for i, item in enumerate(formatted):
        item["rank"] = i + 1
    
    # Return only top_k after re-ranking
    return formatted[:top_k]


# ═══════════════════════════════════════════════════════════════════════════
# GPT ANSWER (optional — uses found context)
# ═══════════════════════════════════════════════════════════════════════════

def generate_answer(
    query: str,
    context_chunks: List[Dict],
    use_strong_model: bool = False,
) -> Dict:
    """
    Generate an answer using YandexGPT based on found context.
    
    Returns: {answer, model, tokens_used, cost_rub, sources}
    """
    model = GPT_MODEL_STRONG if use_strong_model else GPT_MODEL
    model_uri = f"gpt://{YANDEX_FOLDER_ID}/{model}"
    
    # Build context from chunks
    context_parts = []
    sources = []
    for chunk in context_chunks:
        source_ref = f"[{chunk['source']['filename']}, чанк {chunk['source']['chunk_idx']}]"
        context_parts.append(f"{source_ref}:\n{chunk['text']}")
        sources.append({
            "filename": chunk["source"]["filename"],
            "chunk_idx": chunk["source"]["chunk_idx"],
            "score": chunk["score"],
        })
    
    context = "\n\n---\n\n".join(context_parts)
    
    system_prompt = """Ты — ассистент по анализу тендерных документов. 
Отвечай ТОЛЬКО на основе предоставленного контекста.
Если в контексте нет информации для ответа — скажи прямо.
Всегда указывай источник: имя файла и номер фрагмента.
Отвечай кратко и по делу. Не придумывай данные."""

    user_prompt = f"""Контекст из документов:

{context}

---

Вопрос: {query}

Ответь на основе контекста выше. Укажи источники."""

    try:
        resp = requests.post(
            COMPLETION_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {YANDEX_API_KEY}",
                "x-folder-id": YANDEX_FOLDER_ID,
                "x-data-logging-enabled": "false",
            },
            json={
                "modelUri": model_uri,
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.1,
                    "maxTokens": 1000,
                },
                "messages": [
                    {"role": "system", "text": system_prompt},
                    {"role": "user", "text": user_prompt},
                ],
            },
            timeout=60,
        )
        
        if resp.status_code == 200:
            data = resp.json()
            answer_text = data["result"]["alternatives"][0]["message"]["text"]
            usage = data["result"].get("usage", {})
            total_tokens = int(usage.get("totalTokens", 0))
            
            # Cost calculation
            if "lite" in model:
                cost = total_tokens / 1000 * 0.0004  # 0.20₽/1K input + 0.40₽/1K output ≈ avg 0.40₽/1K
            else:
                cost = total_tokens / 1000 * 0.0016  # 0.80₽/1K input + 1.60₽/1K output ≈ avg 1.60₽/1K
            
            return {
                "answer": answer_text,
                "model": model,
                "tokens_used": total_tokens,
                "cost_rub": round(cost, 4),
                "sources": sources,
            }
        else:
            return {
                "answer": f"[ERROR] GPT API {resp.status_code}: {resp.text[:200]}",
                "model": model,
                "tokens_used": 0,
                "cost_rub": 0,
                "sources": sources,
            }
    except Exception as e:
        return {
            "answer": f"[ERROR] GPT request failed: {e}",
            "model": model,
            "tokens_used": 0,
            "cost_rub": 0,
            "sources": sources,
        }


# ═══════════════════════════════════════════════════════════════════════════
# OUTPUT FORMATTING
# ═══════════════════════════════════════════════════════════════════════════

def format_results(query: str, results: List[Dict], answer: Optional[Dict] = None) -> str:
    """Format search results for human-readable output."""
    lines = []
    lines.append(f"\n{'═'*60}")
    lines.append(f"🔍 Запрос: {query}")
    lines.append(f"{'═'*60}")
    
    if not results:
        lines.append("\n  ❌ Ничего не найдено.")
        return "\n".join(lines)
    
    lines.append(f"\n  📋 Найдено {len(results)} релевантных фрагментов:\n")
    
    for r in results:
        score_bar = "█" * int(r["score"] * 10) + "░" * (10 - int(r["score"] * 10))
        lines.append(f"  [{r['rank']}] Score: {r['score']:.3f} {score_bar}")
        lines.append(f"      Источник: {r['source']['filename']} (чанк {r['source']['chunk_idx']})")
        
        # Truncate text for display
        text_preview = r["text"][:300].replace("\n", " ↵ ")
        if len(r["text"]) > 300:
            text_preview += "..."
        lines.append(f"      Текст: {text_preview}")
        lines.append("")
    
    if answer:
        lines.append(f"{'─'*60}")
        lines.append(f"  🤖 Ответ GPT ({answer['model']}):")
        lines.append(f"{'─'*60}")
        lines.append(f"\n{answer['answer']}\n")
        lines.append(f"  📊 Токены: {answer['tokens_used']} | Стоимость: ~{answer['cost_rub']} ₽")
    
    lines.append(f"{'═'*60}\n")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# INTERACTIVE MODE
# ═══════════════════════════════════════════════════════════════════════════

def interactive_mode(tender_id: Optional[str] = None, with_answer: bool = True):
    """Interactive Q&A session."""
    print(f"\n{'═'*60}")
    print(f"  RAG Search — Интерактивный режим")
    if tender_id:
        print(f"  Фильтр: тендер {tender_id}")
    print(f"  Команды: /quit, /stats, /tender <id>, /answer on|off")
    print(f"{'═'*60}\n")
    
    while True:
        try:
            query = input("❓ Вопрос: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nВыход.")
            break
        
        if not query:
            continue
        
        if query == "/quit":
            break
        elif query == "/stats":
            from rag_indexer import show_stats
            show_stats()
            continue
        elif query.startswith("/tender"):
            parts = query.split()
            tender_id = parts[1] if len(parts) > 1 else None
            print(f"  Фильтр: {'все тендеры' if not tender_id else tender_id}")
            continue
        elif query.startswith("/answer"):
            parts = query.split()
            with_answer = parts[1].lower() in ("on", "да", "1") if len(parts) > 1 else not with_answer
            print(f"  GPT-ответ: {'включён' if with_answer else 'выключен'}")
            continue
        
        # Search
        t_start = time.time()
        results = search(query, tender_id=tender_id)
        t_search = time.time() - t_start
        
        # Generate answer if requested
        answer = None
        if with_answer and results:
            answer = generate_answer(query, results)
        
        # Display
        print(format_results(query, results, answer))
        print(f"  ⏱ Поиск: {t_search:.2f} сек")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="RAG Search — семантический поиск по тендерам")
    parser.add_argument("query", nargs="?", help="Поисковый запрос")
    parser.add_argument("--tender-id", help="Фильтр по ID тендера")
    parser.add_argument("--top-k", type=int, default=TOP_K, help="Количество результатов")
    parser.add_argument("--answer", action="store_true", help="Сгенерировать ответ через GPT")
    parser.add_argument("--strong", action="store_true", help="Использовать сильную модель для ответа")
    parser.add_argument("--json", action="store_true", help="JSON-вывод")
    parser.add_argument("--interactive", action="store_true", help="Интерактивный режим")
    parser.add_argument("--collection", default="tenders", help="Имя коллекции ChromaDB")
    
    args = parser.parse_args()
    
    if args.interactive:
        interactive_mode(tender_id=args.tender_id, with_answer=args.answer)
        return
    
    if not args.query:
        parser.print_help()
        sys.exit(1)
    
    # Search
    t_start = time.time()
    results = search(
        args.query,
        tender_id=args.tender_id,
        top_k=args.top_k,
        collection_name=args.collection,
    )
    t_search = time.time() - t_start
    
    # Generate answer if requested
    answer = None
    if args.answer and results:
        answer = generate_answer(args.query, results, use_strong_model=args.strong)
    
    # Output
    if args.json:
        output = {
            "query": args.query,
            "results": results,
            "answer": answer,
            "search_time_sec": round(t_search, 3),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(format_results(args.query, results, answer))
        print(f"  ⏱ Поиск: {t_search:.2f} сек")


if __name__ == "__main__":
    main()
