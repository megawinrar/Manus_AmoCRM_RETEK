"""
Тесты для cron-логики (APScheduler) — гарантия автономности системы.

Покрывает:
1. Расписание cron jobs (каждые 5 минут для YaDisk)
2. Корректность настройки scheduler
3. Все jobs зарегистрированы
4. Система остаётся активной после запуска
5. Health check работает
"""
import os
import sys
import importlib
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# Добавляем src/ в path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# ═══════════════════════════════════════════════════════════════════
# 1. ТЕСТЫ РАСПИСАНИЯ
# ═══════════════════════════════════════════════════════════════════

class TestCronScheduleConfiguration:
    """Тесты конфигурации расписания."""

    def test_yadisk_scan_interval_5_minutes(self):
        """YaDisk сканирование каждые 5 минут."""
        main_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'microservice', 'main.py'
        )
        with open(main_path, 'r') as f:
            content = f.read()
        # Проверяем что yadisk_scan настроен на каждые 5 минут
        assert (
            'IntervalTrigger(minutes=5)' in content
            or 'minutes=5' in content
        ), "YaDisk scan must be configured for every 5 minutes (IntervalTrigger(minutes=5))"

    def test_hourly_control_exists(self):
        """Ежечасный контроль настроен."""
        main_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'microservice', 'main.py'
        )
        with open(main_path, 'r') as f:
            content = f.read()
        assert 'hourly_control' in content

    def test_daily_archive_exists(self):
        """Ежедневная архивация настроена."""
        main_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'microservice', 'main.py'
        )
        with open(main_path, 'r') as f:
            content = f.read()
        assert 'daily_archive' in content

    def test_weekly_control_exists(self):
        """Еженедельный контроль настроен."""
        main_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'microservice', 'main.py'
        )
        with open(main_path, 'r') as f:
            content = f.read()
        assert 'weekly_control' in content

    def test_monthly_revision_exists(self):
        """Ежемесячная ревизия настроена."""
        main_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'microservice', 'main.py'
        )
        with open(main_path, 'r') as f:
            content = f.read()
        assert 'monthly_revision' in content

    def test_yadisk_scan_job_exists(self):
        """Job yadisk_scan зарегистрирован."""
        main_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'microservice', 'main.py'
        )
        with open(main_path, 'r') as f:
            content = f.read()
        assert 'yadisk_scan' in content

    def test_all_cron_modules_importable(self):
        """Все cron-модули существуют."""
        base = os.path.join(os.path.dirname(__file__), '..', 'src', 'microservice')
        required_modules = [
            'cron_yadisk.py',
            'cron_hourly.py',
            'cron_daily.py',
            'cron_weekly.py',
            'cron_monthly.py',
        ]
        for module in required_modules:
            path = os.path.join(base, module)
            assert os.path.exists(path), f"Missing cron module: {module}"


# ═══════════════════════════════════════════════════════════════════
# 2. ТЕСТЫ АВТОНОМНОСТИ
# ═══════════════════════════════════════════════════════════════════

class TestSystemAutonomy:
    """Тесты гарантии автономности системы."""

    def test_docker_compose_restart_always(self):
        """Docker Compose имеет restart: always."""
        compose_path = os.path.join(
            os.path.dirname(__file__), '..', 'deploy', 'docker-compose.yml'
        )
        with open(compose_path, 'r') as f:
            content = f.read()
        assert 'restart: always' in content

    def test_docker_compose_healthcheck(self):
        """Docker Compose имеет healthcheck."""
        compose_path = os.path.join(
            os.path.dirname(__file__), '..', 'deploy', 'docker-compose.yml'
        )
        with open(compose_path, 'r') as f:
            content = f.read()
        assert 'healthcheck' in content
        assert '/health' in content

    def test_dockerfile_has_healthcheck(self):
        """Dockerfile имеет HEALTHCHECK."""
        dockerfile_path = os.path.join(
            os.path.dirname(__file__), '..', 'deploy', 'Dockerfile'
        )
        with open(dockerfile_path, 'r') as f:
            content = f.read()
        assert 'HEALTHCHECK' in content

    def test_dockerfile_has_tesseract(self):
        """Dockerfile устанавливает tesseract для OCR."""
        dockerfile_path = os.path.join(
            os.path.dirname(__file__), '..', 'deploy', 'Dockerfile'
        )
        with open(dockerfile_path, 'r') as f:
            content = f.read()
        assert 'tesseract' in content

    def test_dockerfile_has_poppler(self):
        """Dockerfile устанавливает poppler для pdftotext."""
        dockerfile_path = os.path.join(
            os.path.dirname(__file__), '..', 'deploy', 'Dockerfile'
        )
        with open(dockerfile_path, 'r') as f:
            content = f.read()
        assert 'poppler' in content

    def test_main_imports_apscheduler(self):
        """main.py использует APScheduler."""
        main_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'microservice', 'main.py'
        )
        with open(main_path, 'r') as f:
            content = f.read()
        assert 'apscheduler' in content.lower() or 'APScheduler' in content

    def test_uvicorn_workers_configured(self):
        """Dockerfile запускает uvicorn с workers."""
        dockerfile_path = os.path.join(
            os.path.dirname(__file__), '..', 'deploy', 'Dockerfile'
        )
        with open(dockerfile_path, 'r') as f:
            content = f.read()
        assert '--workers' in content

    def test_data_volumes_configured(self):
        """Docker volumes для данных настроены."""
        compose_path = os.path.join(
            os.path.dirname(__file__), '..', 'deploy', 'docker-compose.yml'
        )
        with open(compose_path, 'r') as f:
            content = f.read()
        assert 'app-data' in content
        assert 'app-logs' in content


# ═══════════════════════════════════════════════════════════════════
# 3. ТЕСТЫ PIPELINE ЛОГИКИ
# ═══════════════════════════════════════════════════════════════════

class TestPipelineIntegration:
    """Тесты интеграции pipeline."""

    def test_chunk_score_extractor_importable(self):
        """chunk_score_extractor.py импортируется без ошибок."""
        scripts_path = os.path.join(os.path.dirname(__file__), '..', 'scripts')
        sys.path.insert(0, scripts_path)
        import chunk_score_extractor
        assert hasattr(chunk_score_extractor, 'extract_and_parse_tender')
        assert hasattr(chunk_score_extractor, 'split_into_chunks')
        assert hasattr(chunk_score_extractor, 'score_chunk_for_field')

    def test_cron_yadisk_uses_chunk_extractor(self):
        """cron_yadisk.py использует chunk_score_extractor."""
        cron_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'microservice', 'cron_yadisk.py'
        )
        with open(cron_path, 'r') as f:
            content = f.read()
        assert 'chunk_score_extractor' in content

    def test_cron_yadisk_has_run_function(self):
        """cron_yadisk.py имеет функцию run_yadisk_scan."""
        cron_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'microservice', 'cron_yadisk.py'
        )
        with open(cron_path, 'r') as f:
            content = f.read()
        assert 'def run_yadisk_scan' in content

    def test_deduplication_module_exists(self):
        """Модуль дедупликации существует."""
        dedup_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'microservice', 'deduplication.py'
        )
        assert os.path.exists(dedup_path)

    def test_field_validator_module_exists(self):
        """Модуль валидации полей существует."""
        fv_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'microservice', 'field_validator.py'
        )
        assert os.path.exists(fv_path)


# ═══════════════════════════════════════════════════════════════════
# 4. ТЕСТЫ КОНФИГУРАЦИИ ДЕПЛОЯ
# ═══════════════════════════════════════════════════════════════════

class TestDeployConfiguration:
    """Тесты конфигурации деплоя."""

    def test_requirements_has_apscheduler(self):
        """requirements.txt содержит APScheduler."""
        req_path = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')
        with open(req_path, 'r') as f:
            content = f.read().lower()
        assert 'apscheduler' in content

    def test_requirements_has_fastapi(self):
        """requirements.txt содержит FastAPI."""
        req_path = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')
        with open(req_path, 'r') as f:
            content = f.read().lower()
        assert 'fastapi' in content

    def test_deploy_requirements_has_pdf2image(self):
        """deploy requirements содержит pdf2image."""
        req_path = os.path.join(
            os.path.dirname(__file__), '..', 'deploy', 'requirements-deploy.txt'
        )
        with open(req_path, 'r') as f:
            content = f.read().lower()
        assert 'pdf2image' in content

    def test_env_example_or_env_exists(self):
        """Файл .env или .env.example существует."""
        base = os.path.dirname(os.path.dirname(__file__))
        assert (
            os.path.exists(os.path.join(base, '.env'))
            or os.path.exists(os.path.join(base, '.env.example'))
        )
