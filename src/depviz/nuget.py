"""Получение зависимостей пакетов из репозитория NuGet.

Используется только HTTP (urllib) и разбор JSON/XML, без менеджеров
пакетов и сторонних библиотек. Для одного пакета:

1. Скачать список сервисов репозитория (``index.json``) и найти
   в нём адрес хранилища пакетов (``PackageBaseAddress/3.0.0``).
2. Скачать список версий пакета и выбрать версию.
3. Скачать описание пакета ``.nuspec`` (XML) и достать зависимости
   из группы для net8.0 или ближайшей совместимой с ней.
"""

import json
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from xml.etree import ElementTree

from depviz.errors import NuGetError

TIMEOUT = 15
HTTP_NOT_FOUND = 404
VERSION_PARTS = 4
BASE_ADDRESS_TYPE = "PackageBaseAddress/3.0.0"
ANY_FRAMEWORK = ""
COMPATIBLE_FRAMEWORKS = (
    "net8.0", "net7.0", "net6.0", "net5.0",
    "netcoreapp3.1", "netcoreapp3.0", "netcoreapp2.2", "netcoreapp2.1",
    "netcoreapp2.0", "netcoreapp1.1", "netcoreapp1.0",
    "netstandard2.1", "netstandard2.0", "netstandard1.6",
    "netstandard1.5", "netstandard1.4", "netstandard1.3",
    "netstandard1.2", "netstandard1.1", "netstandard1.0",
    ANY_FRAMEWORK,
)


class NotFoundError(NuGetError):
    """Сервер ответил 404: такого адреса в репозитории нет."""


def fetch(url):
    """Скачать данные по адресу.

    :param url: адрес.
    :return: содержимое ответа (bytes).
    :raises NotFoundError: если сервер ответил 404.
    :raises NuGetError: если сервер недоступен или ответил ошибкой.
    """
    try:
        with urlopen(url, timeout=TIMEOUT) as response:
            return response.read()
    except HTTPError as error:
        if error.code == HTTP_NOT_FOUND:
            raise NotFoundError(f"не найдено: {url}") from error
        raise NuGetError(
            f"сервер ответил ошибкой {error.code}: {url}"
        ) from error
    except (URLError, OSError) as error:
        raise NuGetError(f"не удалось подключиться: {url}") from error


def fetch_json(url):
    """Скачать и разобрать JSON.

    :param url: адрес.
    :return: разобранные данные.
    :raises NuGetError: если скачать не удалось или это не JSON.
    """
    data = fetch(url)
    try:
        return json.loads(data)
    except ValueError as error:
        raise NuGetError(f"ответ не в формате JSON: {url}") from error


def find_base_address(index):
    """Найти в списке сервисов адрес хранилища пакетов.

    :param index: разобранный ``index.json`` репозитория.
    :return: адрес, оканчивающийся на ``/``.
    :raises NuGetError: если такого сервиса нет.
    """
    resources = index.get("resources") if isinstance(index, dict) else None
    for resource in resources or []:
        if resource.get("@type") == BASE_ADDRESS_TYPE:
            address = resource.get("@id", "")
            return address if address.endswith("/") else address + "/"
    raise NuGetError(
        f"в репозитории нет сервиса {BASE_ADDRESS_TYPE}: "
        "это не репозиторий NuGet v3"
    )


def version_key(version):
    """Ключ для сравнения версий: ``1.2.10`` больше ``1.2.9``.

    Сначала сравниваются числа (недостающие считаются нулями:
    ``1.0`` равно ``1.0.0``), затем стабильная версия считается
    новее предварительной (``2.0.0`` новее ``2.0.0-rc1``), затем
    сравниваются метки (``beta`` раньше ``rc``).

    :param version: строка версии, например ``6.0.0`` или ``2.0.0-rc1``.
    :return: кортеж для сравнения.
    """
    parts = version.split("+")[0].partition("-")
    release, label = parts[0], parts[2]
    numbers = [int(part) if part.isdigit() else 0
               for part in release.split(".")]
    numbers += [0] * (VERSION_PARTS - len(numbers))
    return tuple(numbers), not label, label


def choose_version(versions):
    """Выбрать последнюю стабильную версию (без ``-beta``, ``-rc``).

    Если стабильных версий нет, берётся последняя из всех.

    :param versions: список версий.
    :return: выбранная версия.
    :raises NuGetError: если список пуст.
    """
    if not versions:
        raise NuGetError("у пакета нет ни одной версии")
    stable = [version for version in versions if "-" not in version]
    return max(stable or versions, key=version_key)


def parse_range(text):
    """Разобрать диапазон версий из .nuspec.

    ``1.0`` — не ниже 1.0; ``[1.0]`` — ровно 1.0;
    ``[1.0, 2.0)`` — от 1.0 включительно до 2.0 не включая;
    ``(, 2.0]`` — не выше 2.0.

    :param text: диапазон в записи NuGet.
    :return: кортеж ``(нижняя, включительно, верхняя, включительно)``;
        граница None — без ограничения.
    """
    text = text.strip()
    if not text.startswith(("[", "(")):
        return text or None, True, None, False
    low_inclusive = text.startswith("[")
    high_inclusive = text.endswith("]")
    inner = text[1:-1]
    if "," not in inner:
        exact = inner.strip()
        return exact, True, exact, True
    low, high = (part.strip() or None for part in inner.split(",", 1))
    return low, low_inclusive, high, high_inclusive


def in_range(version, bounds):
    """Проверить, подходит ли версия под диапазон.

    Сравниваются только числа версии.

    :param version: версия.
    :param bounds: результат parse_range.
    :return: True, если подходит.
    """
    low, low_inclusive, high, high_inclusive = bounds
    key = version_key(version)[0]
    if low is not None:
        low_key = version_key(low)[0]
        if key < low_key or (key == low_key and not low_inclusive):
            return False
    if high is not None:
        high_key = version_key(high)[0]
        if key > high_key or (key == high_key and not high_inclusive):
            return False
    return True


def choose_in_range(versions, text):
    """Выбрать самую низкую версию, подходящую под диапазон.

    Так NuGet выбирает версию зависимости. Стабильные версии
    предпочтительнее предварительных.

    :param versions: список версий пакета.
    :param text: диапазон из .nuspec, например ``[8.0.0, 9.0.0)``.
    :return: выбранная версия.
    :raises NuGetError: если подходящей версии нет.
    """
    bounds = parse_range(text)
    matching = [version for version in versions if in_range(version, bounds)]
    stable = [version for version in matching if "-" not in version]
    if not stable and not matching:
        raise NuGetError(f"нет версии, подходящей под диапазон {text}")
    return min(stable or matching, key=version_key)


def get_versions(base, package):
    """Скачать список версий пакета.

    :param base: адрес хранилища пакетов.
    :param package: имя пакета.
    :return: список версий.
    :raises NuGetError: если пакета нет или ответ неверный.
    """
    url = f"{base}{package.lower()}/index.json"
    try:
        data = fetch_json(url)
    except NotFoundError as error:
        raise NuGetError(
            f"пакет {package} не найден в репозитории"
        ) from error
    versions = data.get("versions") if isinstance(data, dict) else None
    if not isinstance(versions, list):
        raise NuGetError(f"неверный список версий: {url}")
    return versions


def local_name(element):
    """Имя XML-тега без пространства имён: ``{...}group`` → ``group``."""
    return element.tag.split("}")[-1]


def normalize_framework(name):
    """Привести имя фреймворка к короткому виду.

    ``.NETStandard2.0`` → ``netstandard2.0``, ``net8.0`` → ``net8.0``.
    """
    return name.strip().lower().lstrip(".")


def parse_groups(nuspec):
    """Достать из .nuspec зависимости по группам фреймворков.

    Зависимости без группы (старый формат) относятся к любому
    фреймворку и попадают в группу ``""``.

    :param nuspec: содержимое .nuspec (bytes).
    :return: словарь «фреймворк → список пар (имя, версия)».
    :raises NuGetError: если это не XML.
    """
    try:
        root = ElementTree.fromstring(nuspec)
    except ElementTree.ParseError as error:
        raise NuGetError("описание пакета .nuspec не в формате XML") from error
    groups = {}
    for element in root.iter():
        if local_name(element) != "dependencies":
            continue
        for child in element:
            if local_name(child) == "group":
                name = normalize_framework(child.get("targetFramework", ""))
                groups[name] = read_dependencies(child)
            elif local_name(child) == "dependency":
                groups.setdefault(ANY_FRAMEWORK, []).append(
                    (child.get("id"), child.get("version", ""))
                )
    return groups


def read_dependencies(group):
    """Прочитать все ``<dependency>`` внутри одной группы.

    :param group: XML-элемент ``<group>``.
    :return: список пар ``(имя, версия)``.
    """
    return [
        (item.get("id"), item.get("version", ""))
        for item in group if local_name(item) == "dependency"
    ]


def choose_group(groups):
    """Выбрать группу для проекта на net8.0.

    Берётся первая группа из COMPATIBLE_FRAMEWORKS: сначала net8.0,
    затем более старые совместимые .NET, .NET Core и .NET Standard,
    в конце — группа для любого фреймворка.

    :param groups: результат parse_groups.
    :return: пара ``(фреймворк, зависимости)``; фреймворк None,
        если совместимой группы нет.
    """
    for framework in COMPATIBLE_FRAMEWORKS:
        if framework in groups:
            return framework, groups[framework]
    return None, []


class NuGetSource:
    """Источник зависимостей: настоящий репозиторий NuGet.

    Для корневого пакета берётся последняя стабильная версия, для
    остальных — самая низкая версия, подходящая под диапазон из
    .nuspec пакета, который первым на них сослался (так выбирает
    версии NuGet). Каждый пакет скачивается только один раз.
    """

    def __init__(self, repository):
        """Создать источник.

        :param repository: URL списка сервисов, например
            ``https://api.nuget.org/v3/index.json``.
        """
        self.repository = repository
        self.base = None
        self.ranges = {}
        self.versions = {}
        self.cache = {}

    def dependencies(self, package):
        """Вернуть прямые зависимости пакета (с запоминанием).

        :param package: имя пакета.
        :return: список имён зависимостей.
        :raises NuGetError: при любой ошибке получения данных.
        """
        if package not in self.cache:
            self.cache[package] = self.load(package)
        return self.cache[package]

    def load(self, package):
        """Скачать версию и .nuspec пакета и прочитать зависимости.

        :param package: имя пакета.
        :return: список имён зависимостей.
        """
        if self.base is None:
            self.base = find_base_address(fetch_json(self.repository))
        versions = get_versions(self.base, package)
        if package in self.ranges:
            version = choose_in_range(versions, self.ranges[package])
        else:
            version = choose_version(versions)
        self.versions[package] = version
        name, number = package.lower(), version.lower()
        nuspec = fetch(f"{self.base}{name}/{number}/{name}.nuspec")
        found = choose_group(parse_groups(nuspec))[1]
        for dependency, version_range in found:
            self.ranges.setdefault(dependency, version_range)
        return [dependency for dependency, version_range in found]
