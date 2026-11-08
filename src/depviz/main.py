"""Точка входа инструмента."""

import argparse
import sys

from depviz.config import format_config, load_config
from depviz.errors import ConfigError

DEFAULT_CONFIG = "config.yaml"
EXIT_OK = 0
EXIT_ERROR = 1


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


def main(argv=None):
    """Прочитать настройки и вывести их в формате ключ-значение.

    :param argv: параметры командной строки.
    :return: код выхода: 0 — успех, 1 — ошибка в настройках.
    """
    args = parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as error:
        print(f"Ошибки в файле настроек {args.config}:", file=sys.stderr)
        for message in error.messages:
            print(f"  - {message}", file=sys.stderr)
        return EXIT_ERROR
    print(format_config(config))
    return EXIT_OK
