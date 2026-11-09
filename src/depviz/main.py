"""Точка входа инструмента."""

import argparse
import sys

from depviz.config import load_config
from depviz.errors import ConfigError, NuGetError
from depviz.nuget import format_dependencies, get_direct_dependencies

DEFAULT_CONFIG = "config.yaml"
EXIT_OK = 0
EXIT_ERROR = 1
TEST_MODE_MESSAGE = (
    "Тестовый режим: граф из файла {repository} будет строиться "
    "на этапе 3."
)


def parse_args(argv=None):
    """Разобрать параметры командной строки.

    :param argv: список параметров; None — взять параметры,
        с которыми запущена программа.
    :return: объект с полем ``config`` — путь к файлу настроек.
    """
    parser = argparse.ArgumentParser(
        prog="depviz",
        description="Визуализатор графа зависимостей NuGet (вариант 12).",
    )
    parser.add_argument(
        "-c", "--config", default=DEFAULT_CONFIG,
        help=f"путь к YAML-файлу настроек (по умолчанию {DEFAULT_CONFIG})",
    )
    return parser.parse_args(argv)


def print_errors(title, messages):
    """Вывести заголовок и список ошибок в поток ошибок.

    :param title: первая строка.
    :param messages: список текстов ошибок.
    """
    print(title, file=sys.stderr)
    for message in messages:
        print(f"  - {message}", file=sys.stderr)


def main(argv=None):
    """Прочитать настройки и вывести прямые зависимости пакета.

    :param argv: параметры командной строки.
    :return: код выхода: 0 — успех, 1 — ошибка.
    """
    args = parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as error:
        print_errors(f"Ошибки в файле настроек {args.config}:",
                     error.messages)
        return EXIT_ERROR
    if config["test_mode"]:
        print(TEST_MODE_MESSAGE.format(repository=config["repository"]))
        return EXIT_OK
    try:
        info = get_direct_dependencies(
            config["repository"], config["package"]
        )
    except NuGetError as error:
        print_errors("Ошибка получения зависимостей:", [str(error)])
        return EXIT_ERROR
    print(format_dependencies(info))
    return EXIT_OK
