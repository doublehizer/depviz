"""Тесты точки входа (без обращения к сети)."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from depviz.errors import NuGetError
from depviz.main import EXIT_ERROR, EXIT_OK, main

CONFIGS_DIR = Path(__file__).parent / "configs"


def run_main(config_path):
    """Запустить main и вернуть код выхода, stdout и stderr."""
    output, errors = io.StringIO(), io.StringIO()
    with redirect_stdout(output), redirect_stderr(errors):
        code = main(["--config", str(config_path)])
    return SimpleNamespace(
        code=code, output=output.getvalue(), errors=errors.getvalue()
    )


class FakeSource:
    """Подмена источника NuGet: два пакета и версия корня."""

    def __init__(self, repository):
        """Запомнить адрес репозитория, как настоящий источник."""
        self.repository = repository
        self.versions = {"Newtonsoft.Json": "13.0.4"}

    def dependencies(self, package):
        """Вернуть зависимости из заготовленного словаря."""
        return {"Newtonsoft.Json": ["Demo"], "Demo": []}[package]


class MainTest(unittest.TestCase):
    """Проверки всего запуска от файла настроек до вывода."""

    def test_test_mode(self):
        """Тестовый режим: граф из файла, без сети."""
        result = run_main(CONFIGS_DIR / "stage3" / "cycle.yaml")
        self.assertEqual(result.code, EXIT_OK)
        self.assertIn("C -> A", result.output)
        self.assertIn("Циклы: C -> A", result.output)

    def test_depth_limit(self):
        """max_depth из настроек передаётся в обход."""
        result = run_main(CONFIGS_DIR / "stage3" / "chain_depth2.yaml")
        self.assertIn("Пакетов в графе: 3", result.output)

    def test_url_mode(self):
        """Обычный режим: граф из источника NuGet (подменённого)."""
        with mock.patch("depviz.main.NuGetSource", FakeSource):
            result = run_main(CONFIGS_DIR / "url_mode.yaml")
        self.assertEqual(result.code, EXIT_OK)
        self.assertIn("Newtonsoft.Json 13.0.4 -> Demo", result.output)

    def test_nuget_error(self):
        """Ошибка репозитория — сообщение в stderr и код ошибки."""
        with mock.patch("depviz.main.NuGetSource",
                        side_effect=NuGetError("нет сети")):
            result = run_main(CONFIGS_DIR / "url_mode.yaml")
        self.assertEqual(result.code, EXIT_ERROR)
        self.assertIn("нет сети", result.errors)

    def test_repository_error(self):
        """Ошибка в файле тестового репозитория — код ошибки."""
        result = run_main(CONFIGS_DIR / "stage3" / "undeclared.yaml")
        self.assertEqual(result.code, EXIT_ERROR)
        self.assertIn("не описан", result.errors)

    def test_config_error(self):
        """Ошибки настроек — в stderr, до построения графа."""
        result = run_main(CONFIGS_DIR / "all_wrong.yaml")
        self.assertEqual(result.code, EXIT_ERROR)
        self.assertIn("max_depth:", result.errors)


if __name__ == "__main__":
    unittest.main()
