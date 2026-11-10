"""Точка входа инструмента."""

import argparse
import sys
from pathlib import Path

from depviz.config import load_config
from depviz.errors import ConfigError, NuGetError, RepoFileError
from depviz.graph import build_graph, format_graph
from depviz.nuget import NuGetSource
from depviz.testrepo import load_test_repository

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


def print_errors(title, messages):
    """Вывести заголовок и список ошибок в поток ошибок.

    :param title: первая строка.
    :param messages: список текстов ошибок.
    """
    print(title, file=sys.stderr)
    for message in messages:
        print(f"  - {message}", file=sys.stderr)


def make_source(config, base_dir):
    """Выбрать источник зависимостей по режиму работы.

    :param config: проверенные параметры.
    :param base_dir: папка файла настроек (путь к тестовому
        репозиторию считается от неё).
    :return: объект с методом ``dependencies(имя)`` и словарём
        ``versions``.
    """
    if config["test_mode"]:
        return load_test_repository(base_dir / config["repository"])
    return NuGetSource(config["repository"])


def main(argv=None):
    """Прочитать настройки, построить граф и вывести его.

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
    try:
        source = make_source(config, Path(args.config).parent)
        graph = build_graph(config["package"], source.dependencies,
                            config["max_depth"], config["filter"])
    except (NuGetError, RepoFileError) as error:
        print_errors("Ошибка построения графа:", [str(error)])
        return EXIT_ERROR
    print(format_graph(graph, source.versions))
    return EXIT_OK
