"""Построение графа зависимостей обходом в глубину (DFS).

Правила обхода:

- глубина корневого пакета — 0, его прямых зависимостей — 1 и т.д.;
  пакет на глубине ``max_depth`` попадает в граф, но его зависимости
  уже не запрашиваются;
- пакеты, в имени которых есть подстрока фильтра (без учёта регистра),
  не попадают в граф, и их зависимости не анализируются;
- если зависимость уже лежит на текущем пути обхода — это цикл:
  ребро запоминается, но второй раз в пакет не заходим;
- пакет, до которого уже дошли, повторно не раскрывается; исключение —
  если теперь до него дошли по более короткому пути (меньшая глубина),
  тогда его зависимости раскрываются заново, чтобы глубина не
  «отрезала» то, что на самом деле в неё помещается.
"""

from dataclasses import dataclass, field

NO_DEPENDENCIES = "(нет зависимостей)"
NOTHING = "нет"
DEPTH_LIMIT = "… (глубже не анализировался: достигнута max_depth)"


@dataclass
class Graph:
    """Результат обхода.

    :ivar root: корневой пакет.
    :ivar edges: словарь «пакет → список зависимостей» в порядке обхода.
    :ivar cycles: рёбра ``(откуда, куда)``, которые замыкают цикл.
    :ivar filtered: пакеты, исключённые фильтром.
    :ivar cut: пакеты, зависимости которых не анализировались
        из-за ограничения глубины.
    """

    root: str
    edges: dict = field(default_factory=dict)
    cycles: list = field(default_factory=list)
    filtered: list = field(default_factory=list)
    cut: list = field(default_factory=list)


class GraphBuilder:
    """Обход графа зависимостей в глубину с рекурсией."""

    def __init__(self, get_dependencies, max_depth, name_filter):
        """Подготовить обход.

        :param get_dependencies: функция «имя пакета → список имён
            его прямых зависимостей».
        :param max_depth: максимальная глубина анализа.
        :param name_filter: подстрока для исключения пакетов
            (пустая строка — без фильтра).
        """
        self.get_dependencies = get_dependencies
        self.max_depth = max_depth
        self.name_filter = name_filter.lower()
        self.graph = None
        self.best_depth = {}
        self.path = []
        self.cut = {}

    def build(self, root):
        """Построить граф, начиная с корневого пакета.

        :param root: имя корневого пакета.
        :return: объект Graph.
        """
        self.graph = Graph(root)
        self.visit(root, 0)
        self.graph.cut = list(self.cut)
        return self.graph

    def is_filtered(self, name):
        """Проверить, исключает ли фильтр пакет с таким именем."""
        return bool(self.name_filter) and self.name_filter in name.lower()

    def visit(self, name, depth):
        """Обработать пакет и рекурсивно — все его зависимости.

        :param name: имя пакета.
        :param depth: глубина пакета (у корня 0).
        """
        if self.best_depth.get(name, depth + 1) <= depth:
            return
        self.best_depth[name] = depth
        self.graph.edges.setdefault(name, [])
        if depth >= self.max_depth:
            self.cut[name] = True
            return
        self.cut.pop(name, None)
        self.path.append(name)
        children = []
        for child in self.get_dependencies(name):
            if self.is_filtered(child):
                self.remember(self.graph.filtered, child)
                continue
            children.append(child)
            if child in self.path:
                self.remember(self.graph.cycles, (name, child))
                continue
            self.visit(child, depth + 1)
        self.graph.edges[name] = children
        self.path.pop()

    @staticmethod
    def remember(items, item):
        """Добавить элемент в список, если его там ещё нет."""
        if item not in items:
            items.append(item)


def build_graph(root, get_dependencies, max_depth, name_filter):
    """Построить граф зависимостей (короткая запись для GraphBuilder).

    :param root: корневой пакет.
    :param get_dependencies: функция «пакет → список зависимостей».
    :param max_depth: максимальная глубина анализа.
    :param name_filter: подстрока фильтра.
    :return: объект Graph.
    """
    builder = GraphBuilder(get_dependencies, max_depth, name_filter)
    return builder.build(root)


def format_graph(graph, versions=None):
    """Сформировать текстовое описание графа для вывода на экран.

    :param graph: объект Graph.
    :param versions: словарь «пакет → версия» (для NuGet) или None.
    :return: многострочный текст.
    """
    versions = versions or {}
    lines = [f"Граф зависимостей пакета {graph.root}:"]
    for name, children in graph.edges.items():
        title = f"{name} {versions[name]}" if name in versions else name
        if name in graph.cut:
            target = DEPTH_LIMIT
        else:
            target = ", ".join(children) or NO_DEPENDENCIES
        lines.append(f"  {title} -> {target}")
    cycles = [f"{start} -> {end}" for start, end in graph.cycles]
    lines.append(f"Пакетов в графе: {len(graph.edges)}")
    lines.append(f"Циклы: {', '.join(cycles) or NOTHING}")
    lines.append(f"Исключены фильтром: {', '.join(graph.filtered) or NOTHING}")
    return "\n".join(lines)
