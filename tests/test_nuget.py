"""Тесты для получения зависимостей из NuGet (без интернета)."""

import io
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

from depviz.errors import NuGetError
from depviz.nuget import (
    ANY_FRAMEWORK, NotFoundError, NuGetSource, choose_group, choose_in_range,
    choose_version, fetch, find_base_address, in_range, parse_groups,
    parse_range, version_key,
)

NUGET_DIR = Path(__file__).parent / "nuget"
BASE = "https://example.org/flat/"


def sample(name):
    """Прочитать пример ответа сервера из tests/nuget."""
    return (NUGET_DIR / name).read_bytes()


class FetchTest(unittest.TestCase):
    """Проверки скачивания и ошибок сети."""

    def test_ok(self):
        """Содержимое ответа возвращается как есть."""
        with mock.patch("depviz.nuget.urlopen",
                        return_value=io.BytesIO(b"data")):
            self.assertEqual(fetch("https://example.org"), b"data")

    def test_not_found(self):
        """Ответ 404 — ошибка «не найдено»."""
        error = HTTPError("https://example.org", 404, "Not Found", {}, None)
        with mock.patch("depviz.nuget.urlopen", side_effect=error):
            with self.assertRaises(NuGetError) as context:
                fetch("https://example.org")
        self.assertIn("не найдено", str(context.exception))

    def test_server_error(self):
        """Другая ошибка сервера — её код в сообщении."""
        error = HTTPError("https://example.org", 500, "Error", {}, None)
        with mock.patch("depviz.nuget.urlopen", side_effect=error):
            with self.assertRaises(NuGetError) as context:
                fetch("https://example.org")
        self.assertIn("500", str(context.exception))

    def test_no_network(self):
        """Сервер недоступен — ошибка подключения."""
        with mock.patch("depviz.nuget.urlopen",
                        side_effect=URLError("no network")):
            with self.assertRaises(NuGetError) as context:
                fetch("https://example.org")
        self.assertIn("подключиться", str(context.exception))


class ServiceIndexTest(unittest.TestCase):
    """Проверки поиска адреса хранилища пакетов."""

    def test_found(self):
        """Адрес берётся из ресурса PackageBaseAddress/3.0.0."""
        index = {"resources": [
            {"@id": "https://example.org/flat",
             "@type": "PackageBaseAddress/3.0.0"},
        ]}
        self.assertEqual(find_base_address(index), BASE)

    def test_missing(self):
        """Нет нужного сервиса — это не репозиторий NuGet."""
        with self.assertRaises(NuGetError):
            find_base_address({"resources": []})

    def test_not_dict(self):
        """Ответ не словарь — ошибка, а не падение программы."""
        with self.assertRaises(NuGetError):
            find_base_address(["resources"])


class VersionTest(unittest.TestCase):
    """Проверки выбора версии."""

    def test_numbers_compared_as_numbers(self):
        """1.2.10 новее, чем 1.2.9."""
        self.assertGreater(version_key("1.2.10"), version_key("1.2.9"))

    def test_stable_newer_than_prerelease(self):
        """2.0.0 новее, чем 2.0.0-rc1."""
        self.assertGreater(version_key("2.0.0"), version_key("2.0.0-rc1"))

    def test_latest_stable(self):
        """Предварительные версии (-rc, -beta) пропускаются."""
        versions = ["1.0.0", "1.2.10", "1.2.9", "2.0.0-rc1"]
        self.assertEqual(choose_version(versions), "1.2.10")

    def test_only_prerelease(self):
        """Если стабильных нет — последняя из всех."""
        versions = ["1.0.0-beta", "1.0.0-rc2"]
        self.assertEqual(choose_version(versions), "1.0.0-rc2")

    def test_empty(self):
        """Пустой список версий — ошибка."""
        with self.assertRaises(NuGetError):
            choose_version([])


class GroupTest(unittest.TestCase):
    """Проверки разбора .nuspec и выбора группы."""

    def test_net8_group(self):
        """Есть группа net8.0 — берётся она, а не net9.0 или net6.0."""
        framework, deps = choose_group(parse_groups(sample("grouped.nuspec")))
        self.assertEqual(framework, "net8.0")
        self.assertEqual(
            deps, [("Logging", "8.0.0"), ("Options", "[8.0.0, 9.0.0)")]
        )

    def test_fallback_to_standard(self):
        """Нет net8.0 — берётся самая новая совместимая .NET Standard."""
        groups = parse_groups(sample("standard_only.nuspec"))
        framework, deps = choose_group(groups)
        self.assertEqual(framework, "netstandard2.0")
        self.assertEqual(deps, [("For.Standard", "2.0.0")])

    def test_legacy_without_groups(self):
        """Старый формат без групп — зависимости для любого фреймворка."""
        framework, deps = choose_group(parse_groups(sample("legacy.nuspec")))
        self.assertEqual(framework, ANY_FRAMEWORK)
        self.assertEqual(deps, [("First", "1.0"), ("Second", "")])

    def test_only_old_framework(self):
        """Только .NET Framework — совместимой группы нет."""
        groups = parse_groups(sample("framework_only.nuspec"))
        self.assertEqual(choose_group(groups), (None, []))

    def test_no_dependencies(self):
        """Нет раздела dependencies — групп нет."""
        self.assertEqual(parse_groups(sample("no_deps.nuspec")), {})

    def test_not_xml(self):
        """Не XML — ошибка."""
        with self.assertRaises(NuGetError):
            parse_groups(b"not xml at all")


class RangeTest(unittest.TestCase):
    """Проверки диапазонов версий из .nuspec."""

    def test_minimum(self):
        """``4.0.0`` — версия 4.0.0 и новее."""
        bounds = parse_range("4.0.0")
        self.assertTrue(in_range("4.0.0", bounds))
        self.assertTrue(in_range("5.1.0", bounds))
        self.assertFalse(in_range("3.9.9", bounds))

    def test_interval(self):
        """``[8.0.0, 9.0.0)`` — от 8.0.0 включительно до 9.0.0."""
        bounds = parse_range("[8.0.0, 9.0.0)")
        self.assertTrue(in_range("8.0.0", bounds))
        self.assertTrue(in_range("8.5.1", bounds))
        self.assertFalse(in_range("9.0.0", bounds))

    def test_exact(self):
        """``[1.0]`` — ровно 1.0 (1.0 и 1.0.0 — одна версия)."""
        bounds = parse_range("[1.0]")
        self.assertTrue(in_range("1.0.0", bounds))
        self.assertFalse(in_range("1.0.1", bounds))

    def test_maximum(self):
        """``(, 2.0]`` — не выше 2.0."""
        bounds = parse_range("(, 2.0]")
        self.assertTrue(in_range("2.0.0", bounds))
        self.assertFalse(in_range("2.0.1", bounds))

    def test_lowest_matching(self):
        """Из подходящих берётся самая низкая стабильная (как в NuGet)."""
        versions = ["3.0.0", "4.0.0-rc1", "4.0.0", "4.1.0", "5.0.0"]
        self.assertEqual(choose_in_range(versions, "4.0.0"), "4.0.0")

    def test_nothing_matches(self):
        """Подходящей версии нет — ошибка."""
        with self.assertRaises(NuGetError):
            choose_in_range(["1.0.0"], "[2.0.0, 3.0.0)")


def nuspec(package, dependencies):
    """Собрать простой .nuspec с группой net8.0.

    :param package: имя пакета.
    :param dependencies: список пар ``(имя, диапазон)``.
    :return: XML в байтах.
    """
    items = "".join(
        f'<dependency id="{name}" version="{version}" />'
        for name, version in dependencies
    )
    return (
        '<package xmlns="http://schemas.microsoft.com/packaging/2013/05/'
        f'nuspec.xsd"><metadata><id>{package}</id><dependencies>'
        f'<group targetFramework="net8.0">{items}</group>'
        "</dependencies></metadata></package>"
    ).encode()


class FakeRepository:
    """Подмена сервера NuGet: отвечает заготовленными данными.

    Пакет Top зависит от Middle (диапазон ``2.0.0``), Middle — от Low.
    Считает запросы, чтобы проверить, что пакеты не скачиваются дважды.
    """

    def __init__(self):
        """Заготовить ответы сервера."""
        self.requests = []
        self.answers = {
            "https://example.org/index.json": sample("index.json"),
            f"{BASE}top/index.json": b'{"versions": ["1.0.0", "1.5.0"]}',
            f"{BASE}top/1.5.0/top.nuspec":
                nuspec("Top", [("Middle", "2.0.0"), ("Low", "1.0.0")]),
            f"{BASE}middle/index.json":
                b'{"versions": ["1.0.0", "2.0.0", "2.1.0", "3.0.0"]}',
            f"{BASE}middle/2.0.0/middle.nuspec":
                nuspec("Middle", [("Low", "1.0.0")]),
            f"{BASE}low/index.json": b'{"versions": ["1.0.0", "1.1.0"]}',
            f"{BASE}low/1.0.0/low.nuspec": nuspec("Low", []),
        }

    def fetch(self, url):
        """Вернуть ответ или ошибку, как настоящий сервер."""
        self.requests.append(url)
        if url not in self.answers:
            raise NotFoundError(f"не найдено: {url}")
        return self.answers[url]


class NuGetSourceTest(unittest.TestCase):
    """Проверки источника зависимостей NuGet на подменённом сервере."""

    def make_source(self):
        """Создать источник и подменить скачивание."""
        server = FakeRepository()
        patcher = mock.patch("depviz.nuget.fetch", server.fetch)
        patcher.start()
        self.addCleanup(patcher.stop)
        return NuGetSource("https://example.org/index.json"), server

    def test_root_latest_dependency_lowest(self):
        """Корень — последняя версия, зависимость — самая низкая."""
        source, server = self.make_source()
        self.assertEqual(source.dependencies("Top"), ["Middle", "Low"])
        self.assertEqual(source.dependencies("Middle"), ["Low"])
        self.assertEqual(source.versions["Top"], "1.5.0")
        self.assertEqual(source.versions["Middle"], "2.0.0")
        self.assertTrue(server.requests)

    def test_cache(self):
        """Повторный запрос пакета не идёт на сервер."""
        source, server = self.make_source()
        source.dependencies("Top")
        count = len(server.requests)
        source.dependencies("Top")
        self.assertEqual(len(server.requests), count)

    def test_unknown_package(self):
        """Пакета нет — понятная ошибка с его именем."""
        source, server = self.make_source()
        with self.assertRaises(NuGetError) as context:
            source.dependencies("Missing")
        self.assertIn("Missing", str(context.exception))
        self.assertTrue(server.requests)


if __name__ == "__main__":
    unittest.main()
