"""Получение прямых зависимостей пакета из репозитория NuGet.

Используется только HTTP (urllib) и разбор JSON/XML, без менеджеров
пакетов и сторонних библиотек. Шаги:

1. Скачать список сервисов репозитория (``index.json``) и найти
   в нём адрес хранилища пакетов (``PackageBaseAddress/3.0.0``).
2. Скачать список версий пакета и выбрать последнюю стабильную.
3. Скачать описание пакета ``.nuspec`` (XML) и достать зависимости
   из группы для net8.0 или ближайшей совместимой с ней.
"""

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from xml.etree import ElementTree

from depviz.errors import NuGetError

TIMEOUT = 15
HTTP_NOT_FOUND = 404
BASE_ADDRESS_TYPE = "PackageBaseAddress/3.0.0"
TARGET_FRAMEWORK = "net8.0"
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


@dataclass
class PackageInfo:
    """Пакет и его прямые зависимости.

    :ivar name: имя пакета.
    :ivar version: выбранная версия пакета.
    :ivar framework: выбранная группа зависимостей; ``""`` — группа
        для любого фреймворка; None — совместимой группы нет.
    :ivar dependencies: список пар ``(имя, версия)``.
    """

    name: str
    version: str
    framework: str
    dependencies: list


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

    Сначала сравниваются числа, затем стабильная версия считается
    новее предварительной (``2.0.0`` новее ``2.0.0-rc1``), затем
    сравниваются метки (``beta`` раньше ``rc``).

    :param version: строка версии, например ``6.0.0`` или ``2.0.0-rc1``.
    :return: кортеж для сравнения.
    """
    parts = version.split("+")[0].partition("-")
    release, label = parts[0], parts[2]
    numbers = tuple(int(part) if part.isdigit() else 0
                    for part in release.split("."))
    return numbers, not label, label


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


def get_direct_dependencies(repository, package):
    """Получить прямые зависимости пакета из репозитория NuGet.

    :param repository: URL списка сервисов, например
        ``https://api.nuget.org/v3/index.json``.
    :param package: имя пакета.
    :return: объект PackageInfo.
    :raises NuGetError: при любой ошибке получения данных.
    """
    base = find_base_address(fetch_json(repository))
    version = choose_version(get_versions(base, package))
    name, number = package.lower(), version.lower()
    nuspec = fetch(f"{base}{name}/{number}/{name}.nuspec")
    groups = parse_groups(nuspec)
    if not groups:
        return PackageInfo(package, version, ANY_FRAMEWORK, [])
    framework, dependencies = choose_group(groups)
    return PackageInfo(package, version, framework, dependencies)


def format_dependencies(info):
    """Сформировать текст со списком прямых зависимостей.

    :param info: объект PackageInfo.
    :return: многострочный текст для вывода на экран.
    """
    if info.framework is None:
        group = f"нет группы, совместимой с {TARGET_FRAMEWORK}"
    else:
        group = info.framework or "для любого фреймворка"
    lines = [
        f"Пакет: {info.name} {info.version}",
        f"Группа зависимостей: {group}",
    ]
    if not info.dependencies:
        lines.append("Прямых зависимостей нет.")
        return "\n".join(lines)
    lines.append(f"Прямые зависимости ({len(info.dependencies)}):")
    for name, version in info.dependencies:
        lines.append(f"  {name} {version}".rstrip())
    return "\n".join(lines)
