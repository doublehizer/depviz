"""Тесты для получения зависимостей из NuGet (без интернета)."""

import io
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

from depviz.errors import NuGetError
from depviz.nuget import (
    ANY_FRAMEWORK, PackageInfo, choose_group, choose_version, fetch,
    find_base_address, format_dependencies, get_direct_dependencies,
    parse_groups, version_key,
)

NUGET_DIR = Path(__file__).parent / "nuget"
REPOSITORY = "https://example.org/index.json"
BASE = "https://example.org/flat/"


def sample(name):
    """Прочитать пример ответа сервера из tests/nuget."""
    return (NUGET_DIR / name).read_bytes()


def fake_server(nuspec_name):
    """Сделать подмену fetch, которая отвечает файлами из tests/nuget.

    :param nuspec_name: какой .nuspec отдавать для пакета demo.
    :return: функция с тем же видом, что и fetch.
    """
    answers = {
        REPOSITORY: sample("index.json"),
        f"{BASE}demo/index.json": sample("versions.json"),
        f"{BASE}demo/1.2.10/demo.nuspec": sample(nuspec_name),
    }

    def fake_fetch(url):
        """Вернуть заготовленный ответ или ошибку «не найдено»."""
        if url not in answers:
            raise NuGetError(f"не найдено: {url}")
        return answers[url]

    return fake_fetch


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


class DirectDependenciesTest(unittest.TestCase):
    """Проверки всей цепочки на подменённом сервере."""

    def test_full_chain(self):
        """index.json → версии → .nuspec → зависимости группы net8.0."""
        with mock.patch("depviz.nuget.fetch", fake_server("grouped.nuspec")):
            info = get_direct_dependencies(REPOSITORY, "Demo")
        self.assertEqual(info.version, "1.2.10")
        self.assertEqual(info.framework, "net8.0")
        self.assertEqual(len(info.dependencies), 2)

    def test_package_without_dependencies(self):
        """Пакет без зависимостей — пустой список."""
        with mock.patch("depviz.nuget.fetch", fake_server("no_deps.nuspec")):
            info = get_direct_dependencies(REPOSITORY, "Demo")
        self.assertEqual(info.dependencies, [])

    def test_unknown_package(self):
        """Пакета нет — понятная ошибка с его именем."""
        with mock.patch("depviz.nuget.fetch", fake_server("no_deps.nuspec")):
            with self.assertRaises(NuGetError):
                get_direct_dependencies(REPOSITORY, "Other")


class FormatTest(unittest.TestCase):
    """Проверки вывода на экран."""

    def test_with_dependencies(self):
        """Выводятся пакет, группа и каждая зависимость."""
        info = PackageInfo("Demo", "1.0.0", "net8.0", [("Logging", "8.0.0")])
        text = format_dependencies(info)
        self.assertIn("Пакет: Demo 1.0.0", text)
        self.assertIn("Группа зависимостей: net8.0", text)
        self.assertIn("  Logging 8.0.0", text)

    def test_without_dependencies(self):
        """Нет зависимостей — так и написано."""
        info = PackageInfo("Demo", "1.0.0", "net6.0", [])
        self.assertIn("Прямых зависимостей нет.", format_dependencies(info))

    def test_no_compatible_group(self):
        """Нет совместимой группы — об этом сообщается."""
        info = PackageInfo("Demo", "1.0.0", None, [])
        self.assertIn("совместимой с net8.0", format_dependencies(info))


if __name__ == "__main__":
    unittest.main()
