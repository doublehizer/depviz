"""Тесты для чтения и проверки файла настроек."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from depviz.config import CHECKS, format_config, load_config, validate
from depviz.errors import ConfigError
from depviz.main import EXIT_ERROR, EXIT_OK, main

TESTS_DIR = Path(__file__).parent
CONFIGS_DIR = TESTS_DIR / "configs"


def make_config(**changes):
    """Собрать правильный набор параметров и заменить часть из них."""
    config = {
        "package": "Newtonsoft.Json",
        "repository": "https://api.nuget.org/v3/index.json",
        "test_mode": False,
        "output_image": "graph.png",
        "ascii_tree": False,
        "max_depth": 3,
        "filter": "",
    }
    config.update(changes)
    return config


class ValidateTest(unittest.TestCase):
    """Проверки отдельных параметров."""

    def assert_error(self, data, message):
        """Проверить, что среди ошибок есть нужное сообщение."""
        with self.assertRaises(ConfigError) as context:
            validate(data, TESTS_DIR)
        self.assertIn(message, str(context.exception))

    def test_valid(self):
        """Правильные параметры возвращаются без изменений."""
        self.assertEqual(validate(make_config(), TESTS_DIR), make_config())

    def test_package(self):
        """Имя пакета с пробелом — ошибка."""
        self.assert_error(make_config(package="a b"), "package:")

    def test_repository_empty(self):
        """Пустой repository — ошибка."""
        self.assert_error(make_config(repository=""), "repository:")

    def test_repository_not_url(self):
        """В обычном режиме repository должен быть URL."""
        self.assert_error(
            make_config(repository="repo.txt"), "нужен URL"
        )

    def test_test_mode_type(self):
        """test_mode — только true или false."""
        self.assert_error(make_config(test_mode="yes"), "test_mode:")

    def test_output_image(self):
        """Имя изображения должно оканчиваться на .png."""
        self.assert_error(make_config(output_image="g.jpg"), ".png")

    def test_ascii_tree_type(self):
        """ascii_tree — только true или false."""
        self.assert_error(make_config(ascii_tree=1), "ascii_tree:")

    def test_max_depth_small(self):
        """Глубина меньше 1 — ошибка."""
        self.assert_error(make_config(max_depth=0), "не меньше 1")

    def test_max_depth_type(self):
        """Глубина — целое число, а не строка или true."""
        self.assert_error(make_config(max_depth="3"), "целое число")
        self.assert_error(make_config(max_depth=True), "целое число")

    def test_filter_type(self):
        """Фильтр — строка."""
        self.assert_error(make_config(filter=5), "filter:")

    def test_missing_param(self):
        """Пропущенный параметр — ошибка."""
        data = make_config()
        del data["max_depth"]
        self.assert_error(data, "max_depth: параметр не задан")

    def test_unknown_param(self):
        """Лишний параметр — ошибка."""
        self.assert_error(make_config(color="red"), "color:")

    def test_not_mapping(self):
        """Список вместо словаря — ошибка."""
        self.assert_error(["package"], "ключ: значение")


class TestModeTest(unittest.TestCase):
    """Проверки тестового режима."""

    def test_valid(self):
        """Файл есть, имя пакета из больших букв."""
        data = make_config(
            package="A", repository="repos/simple.txt", test_mode=True
        )
        self.assertEqual(validate(data, TESTS_DIR)["package"], "A")

    def test_lowercase_package(self):
        """Имя пакета в тестовом режиме — большие буквы."""
        data = make_config(
            package="a", repository="repos/simple.txt", test_mode=True
        )
        with self.assertRaises(ConfigError):
            validate(data, TESTS_DIR)

    def test_missing_file(self):
        """Файла тестового репозитория нет."""
        data = make_config(
            package="A", repository="repos/none.txt", test_mode=True
        )
        with self.assertRaises(ConfigError):
            validate(data, TESTS_DIR)


class LoadConfigTest(unittest.TestCase):
    """Проверки чтения файлов из tests/configs."""

    def test_url_mode(self):
        """Правильный файл в обычном режиме."""
        config = load_config(CONFIGS_DIR / "url_mode.yaml")
        self.assertEqual(list(config), list(CHECKS))

    def test_test_mode(self):
        """Путь к репозиторию считается от папки файла настроек."""
        config = load_config(CONFIGS_DIR / "test_mode.yaml")
        self.assertTrue(config["test_mode"])

    def test_all_wrong(self):
        """В файле со всеми ошибками найдено 7 ошибок."""
        with self.assertRaises(ConfigError) as context:
            load_config(CONFIGS_DIR / "all_wrong.yaml")
        self.assertEqual(len(context.exception.messages), len(CHECKS))

    def test_missing_file(self):
        """Файла настроек нет."""
        with self.assertRaises(ConfigError) as context:
            load_config(CONFIGS_DIR / "no_such_file.yaml")
        self.assertIn("файл не найден", str(context.exception))

    def test_syntax_error(self):
        """Ошибка синтаксиса YAML."""
        with self.assertRaises(ConfigError) as context:
            load_config(CONFIGS_DIR / "syntax_error.yaml")
        self.assertIn("синтаксиса YAML", str(context.exception))


class OutputTest(unittest.TestCase):
    """Проверки вывода параметров."""

    def test_format(self):
        """Каждый параметр выводится строкой «ключ = значение»."""
        text = format_config(make_config())
        self.assertIn("package = Newtonsoft.Json", text)
        self.assertIn("test_mode = false", text)
        self.assertIn('filter = ""', text)
        self.assertEqual(len(text.splitlines()), len(CHECKS))

    def test_main_ok(self):
        """main выводит параметры и возвращает код успеха."""
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--config", str(CONFIGS_DIR / "url_mode.yaml")])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("max_depth = 2", output.getvalue())

    def test_main_error(self):
        """При ошибке main пишет её в stderr и возвращает код ошибки."""
        errors = io.StringIO()
        with redirect_stderr(errors):
            code = main(["--config", str(CONFIGS_DIR / "all_wrong.yaml")])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("max_depth:", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
