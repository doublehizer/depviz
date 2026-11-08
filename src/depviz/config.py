"""Чтение и проверка YAML-файла настроек.

Параметры (все обязательные):

- ``package`` — имя анализируемого пакета;
- ``repository`` — URL репозитория или путь к файлу тестового
  репозитория (путь считается от папки, где лежит файл настроек);
- ``test_mode`` — режим работы с тестовым репозиторием;
- ``output_image`` — имя файла с изображением графа (.png);
- ``ascii_tree`` — выводить ли зависимости ASCII-деревом;
- ``max_depth`` — максимальная глубина анализа (целое, от 1);
- ``filter`` — подстрока для фильтрации пакетов ("" — без фильтра).
"""

import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

from depviz.errors import ConfigError

MIN_DEPTH = 1
IMAGE_SUFFIX = ".png"
URL_SCHEMES = ("http", "https")
PACKAGE_RE = re.compile(r"[A-Za-z0-9_.-]+")
TEST_PACKAGE_RE = re.compile(r"[A-Z]+")


def check_package(value):
    """Проверить имя пакета: буквы, цифры, точка, ``_`` и ``-``."""
    if not isinstance(value, str) or not value:
        return "нужна непустая строка"
    if not PACKAGE_RE.fullmatch(value):
        return "допустимы только латинские буквы, цифры, точка, _ и -"
    return None


def check_repository(value):
    """Проверить, что repository — непустая строка."""
    if not isinstance(value, str) or not value:
        return "нужна непустая строка: URL или путь к файлу"
    return None


def check_flag(value):
    """Проверить логический параметр (true или false)."""
    if not isinstance(value, bool):
        return "нужно true или false"
    return None


def check_output_image(value):
    """Проверить имя файла изображения: строка, оканчивается на .png."""
    if not isinstance(value, str) or not value:
        return "нужна непустая строка"
    if not value.lower().endswith(IMAGE_SUFFIX):
        return f"имя файла должно оканчиваться на {IMAGE_SUFFIX}"
    return None


def check_max_depth(value):
    """Проверить глубину анализа: целое число не меньше MIN_DEPTH."""
    if isinstance(value, bool) or not isinstance(value, int):
        return "нужно целое число"
    if value < MIN_DEPTH:
        return f"должно быть не меньше {MIN_DEPTH}"
    return None


def check_filter(value):
    """Проверить подстроку фильтра: любая строка, можно пустую."""
    if not isinstance(value, str):
        return 'нужна строка (без фильтра — пустая строка "")'
    return None


CHECKS = {
    "package": check_package,
    "repository": check_repository,
    "test_mode": check_flag,
    "output_image": check_output_image,
    "ascii_tree": check_flag,
    "max_depth": check_max_depth,
    "filter": check_filter,
}


def load_config(path):
    """Прочитать файл настроек и проверить все параметры.

    :param path: путь к YAML-файлу.
    :return: словарь параметров в порядке CHECKS.
    :raises ConfigError: если файл не читается или есть ошибки.
    """
    data = read_yaml(path)
    return validate(data, Path(path).parent)


def read_yaml(path):
    """Прочитать YAML-файл.

    :param path: путь к файлу.
    :return: данные из файла.
    :raises ConfigError: если файл не найден, не читается
        или в нём ошибка синтаксиса YAML.
    """
    try:
        with open(path, encoding="utf-8") as file:
            return yaml.safe_load(file)
    except FileNotFoundError as error:
        raise ConfigError([f"файл не найден: {path}"]) from error
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError([f"не удалось прочитать файл: {path}"]) from error
    except yaml.YAMLError as error:
        raise ConfigError([yaml_error_text(error)]) from error


def yaml_error_text(error):
    """Сделать короткое сообщение об ошибке синтаксиса YAML.

    :param error: исключение PyYAML.
    :return: текст с номером строки, если он известен.
    """
    mark = getattr(error, "context_mark", None)
    mark = mark or getattr(error, "problem_mark", None)
    if mark is None:
        return "ошибка синтаксиса YAML"
    return f"ошибка синтаксиса YAML в строке {mark.line + 1}"


def validate(data, base_dir):
    """Проверить параметры и вернуть их в порядке CHECKS.

    Сначала проверяется каждый параметр отдельно, затем —
    согласованность package и repository с режимом test_mode.

    :param data: данные, прочитанные из YAML.
    :param base_dir: папка файла настроек (для путей к файлам).
    :return: словарь параметров.
    :raises ConfigError: со списком всех найденных ошибок.
    """
    if not isinstance(data, dict):
        raise ConfigError(["файл должен содержать пары «ключ: значение»"])
    errors = find_errors(data)
    if not errors:
        errors = check_mode(data, base_dir)
    if errors:
        raise ConfigError(errors)
    return {name: data[name] for name in CHECKS}


def find_errors(data):
    """Найти лишние, пропущенные и неверные параметры.

    :param data: словарь из YAML.
    :return: список текстов ошибок (пустой, если ошибок нет).
    """
    errors = [
        f"{name}: неизвестный параметр" for name in data
        if name not in CHECKS
    ]
    for name, check in CHECKS.items():
        if name not in data:
            errors.append(f"{name}: параметр не задан")
            continue
        message = check(data[name])
        if message:
            errors.append(f"{name}: {message}")
    return errors


def check_mode(config, base_dir):
    """Проверить package и repository с учётом режима test_mode.

    В обычном режиме repository — URL (http или https).
    В тестовом — путь к существующему файлу, а имя пакета
    состоит из больших латинских букв.

    :param config: словарь параметров (типы уже проверены).
    :param base_dir: папка файла настроек.
    :return: список текстов ошибок.
    """
    errors = []
    repository = config["repository"]
    if not config["test_mode"]:
        url = urlparse(repository)
        if url.scheme not in URL_SCHEMES or not url.netloc:
            errors.append(
                "repository: в обычном режиме нужен URL "
                "(http:// или https://)"
            )
        return errors
    if not TEST_PACKAGE_RE.fullmatch(config["package"]):
        errors.append(
            "package: в тестовом режиме имя — большие латинские буквы"
        )
    if not (base_dir / repository).is_file():
        errors.append(
            f"repository: файл тестового репозитория не найден: {repository}"
        )
    return errors


def format_value(value):
    """Показать значение так, как оно записывается в YAML.

    :param value: значение параметра.
    :return: строка: true/false для логических, "" для пустой строки.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value == "":
        return '""'
    return str(value)


def format_config(config):
    """Сформировать вывод параметров в формате ключ-значение.

    :param config: словарь параметров.
    :return: многострочный текст ``ключ = значение``.
    """
    return "\n".join(
        f"{name} = {format_value(value)}" for name, value in config.items()
    )
