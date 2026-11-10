"""Тестовый репозиторий: граф пакетов из текстового файла.

Формат файла — одна строка на пакет::

    A: B C
    B: D
    C: D
    D:

Слева от двоеточия — имя пакета, справа через пробел — его прямые
зависимости. Имена — большие латинские буквы. Каждый пакет, на который
кто-то ссылается, должен быть описан своей строкой (пакет без
зависимостей записывается как ``D:``). Пустые строки и строки-
комментарии (начинаются с символа решётки) пропускаются.
"""

from depviz.config import TEST_PACKAGE_RE
from depviz.errors import RepoFileError

COMMENT = "#"
SEPARATOR = ":"


def load_test_repository(path):
    """Прочитать файл тестового репозитория.

    :param path: путь к файлу.
    :return: объект TestRepository.
    :raises RepoFileError: если файл не читается или формат неверный.
    """
    try:
        with open(path, encoding="utf-8") as file:
            lines = file.read().splitlines()
    except FileNotFoundError as error:
        raise RepoFileError(
            f"файл тестового репозитория не найден: {path}"
        ) from error
    except (OSError, UnicodeDecodeError) as error:
        raise RepoFileError(
            f"не удалось прочитать тестовый репозиторий: {path}"
        ) from error
    return TestRepository(parse_lines(lines))


def parse_lines(lines):
    """Разобрать строки файла в словарь «пакет → зависимости».

    :param lines: строки файла.
    :return: словарь в порядке строк файла.
    :raises RepoFileError: с номером строки, если она неверная.
    """
    packages = {}
    mentioned = {}
    for number, line in enumerate(lines, start=1):
        text = line.strip()
        if not text or text.startswith(COMMENT):
            continue
        name, dependencies = parse_line(text, number)
        if name in packages:
            raise RepoFileError(
                f"строка {number}: пакет {name} уже описан выше"
            )
        packages[name] = dependencies
        for dependency in dependencies:
            mentioned.setdefault(dependency, number)
    for name, number in mentioned.items():
        if name not in packages:
            raise RepoFileError(
                f"строка {number}: пакет {name} упоминается, но не описан"
            )
    return packages


def parse_line(text, number):
    """Разобрать одну строку вида ``A: B C``.

    :param text: строка без пробелов по краям.
    :param number: номер строки (для сообщений об ошибках).
    :return: пара ``(имя, список зависимостей без повторов)``.
    :raises RepoFileError: если нет двоеточия или имя неверное.
    """
    if SEPARATOR not in text:
        raise RepoFileError(
            f"строка {number}: нужен формат «ПАКЕТ: ЗАВИСИМОСТИ»"
        )
    left, right = text.split(SEPARATOR, 1)
    name = left.strip()
    dependencies = list(dict.fromkeys(right.split()))
    for item in [name, *dependencies]:
        if not TEST_PACKAGE_RE.fullmatch(item):
            raise RepoFileError(
                f"строка {number}: имя «{item}» — нужны только "
                "большие латинские буквы"
            )
    return name, dependencies


class TestRepository:
    """Источник зависимостей: граф пакетов из файла."""

    def __init__(self, packages):
        """Создать репозиторий.

        :param packages: словарь «пакет → список зависимостей».
        """
        self.packages = packages
        self.versions = {}

    def dependencies(self, package):
        """Вернуть прямые зависимости пакета.

        :param package: имя пакета.
        :return: список имён.
        :raises RepoFileError: если такого пакета нет.
        """
        if package not in self.packages:
            raise RepoFileError(
                f"пакет {package} не найден в тестовом репозитории"
            )
        return self.packages[package]
