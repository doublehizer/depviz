"""Тесты для файла тестового репозитория."""

import unittest
from pathlib import Path

from depviz.errors import RepoFileError
from depviz.testrepo import load_test_repository, parse_lines

REPOS_DIR = Path(__file__).parent / "repos"


class ParseTest(unittest.TestCase):
    """Проверки разбора строк файла."""

    def assert_error(self, lines, message):
        """Проверить, что разбор строк даёт ошибку с сообщением."""
        with self.assertRaises(RepoFileError) as context:
            parse_lines(lines)
        self.assertIn(message, str(context.exception))

    def test_valid(self):
        """Пакеты и зависимости читаются в порядке файла."""
        packages = parse_lines(["A: B C", "B:", "C: B"])
        self.assertEqual(packages, {"A": ["B", "C"], "B": [], "C": ["B"]})

    def test_comments_and_blank_lines(self):
        """Комментарии и пустые строки пропускаются."""
        packages = parse_lines(["# граф", "", "A:"])
        self.assertEqual(packages, {"A": []})

    def test_repeated_dependency(self):
        """Повтор зависимости в строке не создаёт двойное ребро."""
        self.assertEqual(parse_lines(["A: B B", "B:"])["A"], ["B"])

    def test_no_colon(self):
        """Нет двоеточия — ошибка с номером строки."""
        self.assert_error(["A: B", "B C"], "строка 2")

    def test_lowercase_name(self):
        """Имя не из больших латинских букв — ошибка."""
        self.assert_error(["a: B", "B:"], "большие латинские буквы")

    def test_duplicate(self):
        """Пакет описан дважды — ошибка."""
        self.assert_error(["A:", "A:"], "уже описан")

    def test_undeclared(self):
        """Ссылка на неописанный пакет — ошибка."""
        self.assert_error(["A: B"], "не описан")


class LoadTest(unittest.TestCase):
    """Проверки чтения файла."""

    def test_load(self):
        """Файл из tests/repos читается, зависимости отдаются."""
        repository = load_test_repository(REPOS_DIR / "simple.txt")
        self.assertEqual(repository.dependencies("A"), ["B", "C"])
        self.assertEqual(repository.versions, {})

    def test_unknown_package(self):
        """Пакета нет в репозитории — ошибка."""
        repository = load_test_repository(REPOS_DIR / "simple.txt")
        with self.assertRaises(RepoFileError):
            repository.dependencies("Z")

    def test_missing_file(self):
        """Файла нет — ошибка."""
        with self.assertRaises(RepoFileError):
            load_test_repository(REPOS_DIR / "no_such_file.txt")


if __name__ == "__main__":
    unittest.main()
