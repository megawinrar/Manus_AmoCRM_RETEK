#!/usr/bin/env python3
"""
Pipeline Tender — Полный пайплайн обработки тендера.

    Файлы → Extract → Classify → Index (RAG) → [Create Deal]

Объединяет:
    1. extract_and_classify.py — экстракция + regex-парсинг + confidence
    2. rag_indexer.py — чанкование + embedding + ChromaDB
    3. emulate_llm_with_dedup.py — создание сделки в amoCRM (опционально)

Использование:
    # Полный пайплайн (extract + classify + index)
    python3 scripts/pipeline_tender.py --files file1.pdf file2.docx --tender-id "2109-2026-00743"

    # С автосозданием сделки в amoCRM
    python3 scripts/pipeline_tender.py --files *.pdf *.docx --tender-id "2109-2026-00743" --create-deal

    # Из папки
    python3 scripts/pipeline_tender.py --folder /path/to/tender

    # Только индексация (без классификации)
    python3 scripts/pipeline_tender.py --files *.pdf --tender-id "xxx" --index-only
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline(
    files: List[str],
    tender_id: Optional[str] = None,
    create_deal: bool = False,
    index_only: bool = False,
    verbose: bool = True,
) -> Dict:
    """
    Run the full tender processing pipeline.
    
    Steps:
    1. Extract text from all files
    2. Parse fields (regex) + validate (confidence scoring)
    3. Index into ChromaDB (RAG)
    4. Optionally create deal in amoCRM
    
    Returns pipeline result dict.
    """
    result = {
        "status": "ok",
        "tender_id": tender_id,
        "steps": {},
        "timing": {},
        "errors": [],
    }
    
    t_total = time.time()
    
    # ─── Step 1+2: Extract & Classify ────────────────────────────────
    if not index_only:
        if verbose:
            print(f"\n{'═'*60}")
            print(f"  PIPELINE: Extract + Classify")
            print(f"{'═'*60}")
        
        t_step = time.time()
        
        try:
            # Import extract_and_classify functions
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "extract_and_classify",
                str(PROJECT_ROOT / "scripts" / "extract_and_classify.py")
            )
            ec_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ec_module)
            
            # Run extraction
            # The module expects command-line args, so we call its internals
            all_text = ""
            file_texts = {}
            for f in files:
                if os.path.exists(f):
                    text = ec_module.extract_file(f)
                    if isinstance(text, tuple):
                        text = text[0]  # (text, method) tuple
                    file_texts[f] = text
                    all_text += text + "\n"
            
            # Parse fields
            parsed = ec_module.parse_fields(all_text, files)
            
            # Use tender_id from parsed if not provided
            if not tender_id:
                tender_id = parsed.get("procedure_number") or "unknown"
                result["tender_id"] = tender_id
            
            result["steps"]["extract_classify"] = {
                "files_processed": len(file_texts),
                "total_chars": len(all_text),
                "parsed_fields": {k: v for k, v in parsed.items() 
                                  if k not in ("confidence_scores", "ocr_applied", "validation_status")},
                "confidence_scores": parsed.get("confidence_scores", {}),
                "validation_status": parsed.get("validation_status", "unknown"),
            }
            
            if verbose:
                print(f"\n  ✅ Классификация: {parsed.get('validation_status', '?')}")
                print(f"     Заказчик: {parsed.get('customer', '?')}")
                print(f"     НМЦ: {parsed.get('nmc', '?')}")
                print(f"     Дедлайн: {parsed.get('deadline', '?')}")
                print(f"     Направление: {parsed.get('direction_hint', '?')}")
                print(f"     Приоритет: {parsed.get('priority_hint', '?')}")
            
        except Exception as e:
            result["errors"].append(f"Extract/Classify failed: {e}")
            result["steps"]["extract_classify"] = {"error": str(e)}
            if verbose:
                print(f"\n  ❌ Ошибка: {e}")
        
        result["timing"]["extract_classify_sec"] = round(time.time() - t_step, 2)
    
    # ─── Step 3: RAG Indexing ────────────────────────────────────────
    if verbose:
        print(f"\n{'═'*60}")
        print(f"  PIPELINE: RAG Indexing")
        print(f"{'═'*60}")
    
    t_step = time.time()
    
    try:
        from rag_indexer import index_tender
        
        tender_name = ""
        if not index_only and "extract_classify" in result["steps"]:
            ec = result["steps"]["extract_classify"]
            if "parsed_fields" in ec:
                customer = ec["parsed_fields"].get("customer", "")
                tender_name = f"{customer} — {tender_id}"
        
        index_stats = index_tender(
            files=files,
            tender_id=tender_id or "unknown",
            tender_name=tender_name,
        )
        
        result["steps"]["rag_index"] = index_stats
        
    except Exception as e:
        result["errors"].append(f"RAG indexing failed: {e}")
        result["steps"]["rag_index"] = {"error": str(e)}
        if verbose:
            print(f"\n  ❌ Ошибка индексации: {e}")
    
    result["timing"]["rag_index_sec"] = round(time.time() - t_step, 2)
    
    # ─── Step 4: Create Deal (optional) ──────────────────────────────
    if create_deal and not index_only:
        if verbose:
            print(f"\n{'═'*60}")
            print(f"  PIPELINE: Create Deal in amoCRM")
            print(f"{'═'*60}")
        
        # Check if validation passed
        ec_step = result["steps"].get("extract_classify", {})
        validation = ec_step.get("validation_status", "unknown")
        
        if validation == "blocked":
            result["steps"]["create_deal"] = {
                "status": "blocked",
                "reason": "Validation failed — required fields missing",
            }
            if verbose:
                print(f"\n  ⛔ Создание сделки заблокировано: не все поля найдены")
        elif validation == "warnings":
            result["steps"]["create_deal"] = {
                "status": "skipped",
                "reason": "Warnings present — manual review recommended",
            }
            if verbose:
                print(f"\n  ⚠️ Есть предупреждения — рекомендуется ручная проверка")
        else:
            # TODO: integrate with emulate_llm_with_dedup.py
            result["steps"]["create_deal"] = {
                "status": "ready",
                "reason": "All fields validated. Run emulate_llm_with_dedup.py to create.",
                "command": f"python3 scripts/emulate_llm_with_dedup.py --files {' '.join(files)}",
            }
            if verbose:
                print(f"\n  ✅ Готово к созданию сделки")
                print(f"     Запустите: python3 scripts/emulate_llm_with_dedup.py --files {' '.join(files[:2])}...")
    
    # ─── Summary ─────────────────────────────────────────────────────
    result["timing"]["total_sec"] = round(time.time() - t_total, 2)
    
    if result["errors"]:
        result["status"] = "errors"
    
    if verbose:
        print(f"\n{'═'*60}")
        print(f"  PIPELINE COMPLETE")
        print(f"{'═'*60}")
        print(f"  Статус: {result['status']}")
        print(f"  Время: {result['timing']['total_sec']} сек")
        if result["errors"]:
            print(f"  Ошибки: {result['errors']}")
        print(f"{'═'*60}\n")
    
    return result


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Pipeline Tender — полный пайплайн обработки")
    parser.add_argument("--files", nargs="+", help="Файлы тендера")
    parser.add_argument("--folder", help="Папка с файлами тендера")
    parser.add_argument("--tender-id", help="ID тендера (номер закупки)")
    parser.add_argument("--create-deal", action="store_true", help="Создать сделку в amoCRM")
    parser.add_argument("--index-only", action="store_true", help="Только индексация (без классификации)")
    parser.add_argument("--json", action="store_true", help="JSON-вывод")
    parser.add_argument("--quiet", action="store_true", help="Минимальный вывод")
    
    args = parser.parse_args()
    
    # Collect files
    files = []
    if args.files:
        files = [f for f in args.files if os.path.exists(f)]
    elif args.folder:
        folder = Path(args.folder)
        if folder.is_dir():
            for ext in ("*.pdf", "*.docx", "*.xlsx", "*.doc", "*.xls"):
                files.extend(str(f) for f in folder.glob(ext))
    
    if not files:
        print("[ERROR] No files found")
        parser.print_help()
        sys.exit(1)
    
    # Run pipeline
    result = run_pipeline(
        files=files,
        tender_id=args.tender_id,
        create_deal=args.create_deal,
        index_only=args.index_only,
        verbose=not args.quiet,
    )
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
