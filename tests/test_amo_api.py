"""
tests/test_amo_api.py — Unit-тесты для amoCRM скриптов RETEK

Запуск всех тестов:
    python3 -m pytest tests/ -v

Запуск с покрытием:
    python3 -m pytest tests/ -v --tb=short

Тесты используют mock — реальных API-запросов НЕ делают.
"""

import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные фикстуры
# ─────────────────────────────────────────────────────────────────────────────

def make_status(sid, name, sort=10, color="#fffeb2", stype=0):
    return {"id": sid, "name": name, "sort": sort, "color": color, "type": stype}


def make_pipeline(pid, name, statuses=None):
    return {
        "id": pid,
        "name": name,
        "_embedded": {"statuses": statuses or []}
    }


# ─────────────────────────────────────────────────────────────────────────────
# Тесты конфигурации статусов
# ─────────────────────────────────────────────────────────────────────────────

class TestStatusConfig(unittest.TestCase):
    """Проверяем корректность определения статусов без обращения к API."""

    def _load_statuses(self):
        """Импортируем ACTIVE_STATUSES из fix_statuses.py через importlib."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "fix_statuses",
            str(Path(__file__).parent.parent / "src" / "fix_statuses.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return {"ACTIVE_STATUSES": mod.ACTIVE_STATUSES}

    def test_active_statuses_count(self):
        """Активная воронка должна содержать ровно 10 статусов."""
        ns = self._load_statuses()
        self.assertEqual(len(ns["ACTIVE_STATUSES"]), 10)

    def test_active_statuses_have_names(self):
        """Все статусы должны иметь непустые имена."""
        ns = self._load_statuses()
        for s in ns["ACTIVE_STATUSES"]:
            self.assertTrue(s["name"].strip(), f"Пустое имя у статуса: {s}")

    def test_active_statuses_have_descriptions(self):
        """Все статусы должны иметь описание (desc)."""
        ns = self._load_statuses()
        for s in ns["ACTIVE_STATUSES"]:
            self.assertIn("desc", s, f"Нет поля desc у статуса: {s['name']}")
            self.assertTrue(s["desc"].strip(), f"Пустое описание у: {s['name']}")

    def test_active_statuses_sorts_unique(self):
        """Значения sort должны быть уникальными."""
        ns = self._load_statuses()
        sorts = [s["sort"] for s in ns["ACTIVE_STATUSES"]]
        self.assertEqual(len(sorts), len(set(sorts)), "Дублирующиеся sort значения")

    def test_active_statuses_colors_valid(self):
        """Цвета должны быть None или строкой вида #rrggbb."""
        import re
        ns = self._load_statuses()
        pattern = re.compile(r"^#[0-9a-f]{6}$")
        forbidden_greys = {"#d6d6d6", "#c1c1c1", "#aaaaaa"}
        for s in ns["ACTIVE_STATUSES"]:
            c = s["color"]
            if c is not None:
                self.assertRegex(c, pattern, f"Неверный формат цвета у {s['name']}: {c}")
                self.assertNotIn(c, forbidden_greys,
                    f"Серый цвет {c} не принимается amoCRM API у статуса {s['name']}")

    def test_active_statuses_names_numbered(self):
        """Имена активных статусов должны начинаться с номера."""
        ns = self._load_statuses()
        for i, s in enumerate(ns["ACTIVE_STATUSES"], 1):
            self.assertTrue(
                s["name"].startswith(f"{i}."),
                f"Статус #{i} должен начинаться с '{i}.', получено: {s['name']}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Тесты dry-run логики
# ─────────────────────────────────────────────────────────────────────────────

class TestDryRun(unittest.TestCase):
    """Проверяем что dry-run не делает реальных запросов."""

    @patch("requests.post")
    @patch("requests.patch")
    @patch("requests.delete")
    @patch("requests.get")
    def test_dry_run_makes_no_write_requests(self, mock_get, mock_delete, mock_patch, mock_post):
        """В режиме dry-run POST/PATCH/DELETE не должны вызываться."""
        # Симулируем ответ GET с существующими статусами
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "_embedded": {
                    "statuses": [
                        make_status(86352246, "Неразобранное", stype=10000),
                        make_status(86357001, "Старый статус"),
                        make_status(142, "Успешно реализовано"),
                        make_status(143, "Закрыто и не реализовано"),
                    ]
                }
            }
        )

        # Импортируем и запускаем dry-run
        from fix_statuses import dry_run_report
        report = dry_run_report(pipeline_id=10984442)

        # Проверяем что write-запросы не делались
        mock_post.assert_not_called()
        mock_patch.assert_not_called()
        mock_delete.assert_not_called()

        # Проверяем структуру отчёта
        self.assertIn("to_delete", report)
        self.assertIn("to_create", report)
        self.assertEqual(len(report["to_create"]), 10)  # 10 статусов RETEK


# ─────────────────────────────────────────────────────────────────────────────
# Тесты API-клиента
# ─────────────────────────────────────────────────────────────────────────────

class TestApiClient(unittest.TestCase):
    """Тесты вспомогательных API-функций."""

    @patch("requests.get")
    def test_get_statuses_returns_list(self, mock_get):
        """api_get должен возвращать список статусов."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "_embedded": {
                    "statuses": [make_status(1, "Test")]
                }
            }
        )
        mock_get.return_value.raise_for_status = MagicMock()

        from fix_statuses import get_statuses
        result = get_statuses(12345)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Test")

    @patch("requests.delete")
    def test_delete_skips_system_statuses(self, mock_delete):
        """delete_custom_statuses не должен трогать статусы 142 и 143."""
        mock_delete.return_value = MagicMock(status_code=204)

        statuses = [
            make_status(142, "Успешно реализовано"),
            make_status(143, "Закрыто и не реализовано"),
            make_status(86357001, "Кастомный"),
        ]

        from fix_statuses import delete_custom_statuses
        delete_custom_statuses(10984442, statuses)

        # Должен удалить только кастомный
        self.assertEqual(mock_delete.call_count, 1)
        called_url = mock_delete.call_args[0][0]
        self.assertIn("86357001", called_url)

    @patch("requests.delete")
    def test_delete_skips_unsorted(self, mock_delete):
        """delete_custom_statuses не должен трогать Неразобранное (type=10000)."""
        mock_delete.return_value = MagicMock(status_code=204)

        statuses = [
            make_status(86352246, "Неразобранное", stype=10000),
            make_status(86357001, "Кастомный"),
        ]

        from fix_statuses import delete_custom_statuses
        delete_custom_statuses(10984442, statuses)

        self.assertEqual(mock_delete.call_count, 1)
        called_url = mock_delete.call_args[0][0]
        self.assertIn("86357001", called_url)

    @patch("requests.patch")
    @patch("requests.post")
    def test_create_status_sends_name_and_color(self, mock_post, mock_patch):
        """Создание статуса: POST с именем, затем PATCH с именем+цветом."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"_embedded": {"statuses": [make_status(99999, "Тест")]}}
        )
        mock_post.return_value.raise_for_status = MagicMock()
        mock_patch.return_value = MagicMock(status_code=200, json=lambda: {})
        mock_patch.return_value.raise_for_status = MagicMock()

        from fix_statuses import create_status_with_name_and_color
        sid = create_status_with_name_and_color(10984442, "Тест", "#fffeb2", 10)

        self.assertEqual(sid, 99999)

        # POST должен содержать имя
        post_payload = mock_post.call_args[1]["json"]
        self.assertEqual(post_payload[0]["name"], "Тест")

        # PATCH должен содержать имя И цвет (чтобы имя не сбрасывалось)
        patch_payload = mock_patch.call_args[1]["json"]
        self.assertEqual(patch_payload["name"], "Тест")
        self.assertEqual(patch_payload["color"], "#fffeb2")

    @patch("requests.patch")
    @patch("requests.post")
    def test_create_status_no_patch_for_default_color(self, mock_post, mock_patch):
        """Если цвет None — PATCH не должен вызываться."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"_embedded": {"statuses": [make_status(99999, "Тест")]}}
        )
        mock_post.return_value.raise_for_status = MagicMock()

        from fix_statuses import create_status_with_name_and_color
        create_status_with_name_and_color(10984442, "Тест", None, 10)

        mock_patch.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Тесты конфигурации воронок
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineConfig(unittest.TestCase):
    """Проверяем конфигурацию воронок из setup_pipelines.py."""

    def _load_pipeline_config(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "setup_pipelines",
            str(Path(__file__).parent.parent / "src" / "setup_pipelines.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return {
            "ACTIVE_PIPELINE_NAME": mod.ACTIVE_PIPELINE_NAME,
            "ARCHIVE_DIR_PIPELINE_NAME": mod.ARCHIVE_DIR_PIPELINE_NAME,
            "ARCHIVE_SOZ_PIPELINE_NAME": mod.ARCHIVE_SOZ_PIPELINE_NAME,
            "ARCHIVE_DIR_STATUSES": mod.ARCHIVE_DIR_STATUSES,
            "ARCHIVE_SOZ_STATUSES": mod.ARCHIVE_SOZ_STATUSES,
        }

    def test_pipeline_names_defined(self):
        """Все три воронки должны иметь имена."""
        ns = self._load_pipeline_config()
        self.assertTrue(ns["ACTIVE_PIPELINE_NAME"])
        self.assertTrue(ns["ARCHIVE_DIR_PIPELINE_NAME"])
        self.assertTrue(ns["ARCHIVE_SOZ_PIPELINE_NAME"])

    def test_archive_statuses_have_colors(self):
        """Архивные статусы должны иметь цвет или None."""
        import re
        ns = self._load_pipeline_config()
        pattern = re.compile(r"^#[0-9a-f]{6}$")
        for s in ns["ARCHIVE_DIR_STATUSES"] + ns["ARCHIVE_SOZ_STATUSES"]:
            c = s["color"]
            if c is not None:
                self.assertRegex(c, pattern, f"Неверный цвет у {s['name']}: {c}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
