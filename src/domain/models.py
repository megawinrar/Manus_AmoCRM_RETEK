"""
Domain models for RETEK amoCRM.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TenderFile:
    """Запись о файле тендера."""
    filename: str
    file_hash: str
    source_path: str
    file_size: int = 0


@dataclass
class DeduplicationResult:
    """Результат проверки на дубль."""
    is_new: bool = False
    is_exact_duplicate: bool = False
    is_enrichment: bool = False
    is_update: bool = False
    is_fuzzy_duplicate: bool = False
    existing_lead_id: Optional[int] = None


@dataclass
class ClassificationResult:
    """Результат классификации тендера."""
    customer: str = ""
    nmc: Optional[float] = None
    direction: str = ""
    priority: str = ""
    situation_type: str = ""
    deadline: str = ""
    confidence: float = 0.0


@dataclass
class ValidationResult:
    """Результат проверки полей."""
    is_valid: bool = False
    missing_fields: list = None
    error_message: str = ""
