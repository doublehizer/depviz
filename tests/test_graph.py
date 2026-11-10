"""Тесты для построения графа обходом в глубину."""

import unittest

from depviz.graph import NO_DEPENDENCIES, build_graph, format_graph

CHAIN = {"A": ["B"], "B": ["C"], "C": ["D"], "D": []}
DIAMOND = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
CYCLE = {"A": ["B"], "B": ["C"], "C": ["A"]}
DEEP_LIMIT = 10


def graph_of(packages, root="A", max_depth=DEEP_LIMIT, name_filter=""):
    """Построить граф по словарю «пакет → зависимости»."""
    return build_graph(root, packages.__getitem__, max_depth, name_filter)


class DepthTest(unittest.TestCase):
    """Проверки ограничения глубины."""

    def test_full_chain(self):
        """Без ограничения проходится вся цепочка."""
        graph = graph_of(CHAIN)
        self.assertEqual(list(graph.edges), ["A", "B", "C", "D"])
        self.assertEqual(graph.cut, [])

    def test_depth_one(self):
        """max_depth 1 — только прямые зависимости."""
        graph = graph_of(CHAIN, max_depth=1)
        self.assertEqual(graph.edges, {"A": ["B"], "B": []})
        self.assertEqual(graph.cut, ["B"])

    def test_shorter_path_wins(self):
        """C сначала найден глубоко, потом ближе — раскрывается заново."""
        packages = {"A": ["B", "C"], "B": ["C"], "C": ["D"], "D": []}
        graph = graph_of(packages, max_depth=2)
        self.assertEqual(graph.edges["C"], ["D"])
        self.assertIn("D", graph.edges)
        self.assertEqual(graph.cut, ["D"])


class CycleTest(unittest.TestCase):
    """Проверки циклов и общих зависимостей."""

    def test_cycle(self):
        """Цикл найден, обход не зацикливается."""
        graph = graph_of(CYCLE)
        self.assertEqual(graph.cycles, [("C", "A")])
        self.assertEqual(graph.edges["C"], ["A"])

    def test_self_loop(self):
        """Пакет, зависящий сам от себя, — тоже цикл."""
        graph = graph_of({"A": ["A", "B"], "B": []})
        self.assertEqual(graph.cycles, [("A", "A")])

    def test_diamond_is_not_cycle(self):
        """Общая зависимость D — не цикл, в графе она один раз."""
        calls = []

        def counting(name):
            """Запомнить запрос и вернуть зависимости."""
            calls.append(name)
            return DIAMOND[name]

        graph = build_graph("A", counting, DEEP_LIMIT, "")
        self.assertEqual(graph.cycles, [])
        self.assertEqual(calls.count("D"), 1)
        self.assertEqual(len(graph.edges), len(DIAMOND))


class FilterTest(unittest.TestCase):
    """Проверки фильтра по подстроке."""

    def test_subtree_removed(self):
        """Исключённый пакет и то, что доступно только через него."""
        graph = graph_of(CHAIN, name_filter="C")
        self.assertEqual(graph.edges, {"A": ["B"], "B": []})
        self.assertEqual(graph.filtered, ["C"])

    def test_ignore_case(self):
        """Фильтр не учитывает регистр."""
        graph = graph_of(CHAIN, name_filter="b")
        self.assertEqual(graph.filtered, ["B"])

    def test_empty_filter(self):
        """Пустой фильтр ничего не исключает."""
        self.assertEqual(graph_of(CHAIN).filtered, [])


class FormatTest(unittest.TestCase):
    """Проверки вывода графа."""

    def test_text(self):
        """В выводе рёбра, циклы, число пакетов и отметка листа."""
        text = format_graph(graph_of({"A": ["B", "A"], "B": []}))
        self.assertIn("  A -> B, A", text)
        self.assertIn(f"  B -> {NO_DEPENDENCIES}", text)
        self.assertIn("Циклы: A -> A", text)
        self.assertIn("Пакетов в графе: 2", text)

    def test_versions_and_depth(self):
        """Версии показываются, нераскрытые пакеты отмечены."""
        graph = graph_of(CHAIN, max_depth=1)
        text = format_graph(graph, {"A": "1.0.0"})
        self.assertIn("  A 1.0.0 -> B", text)
        self.assertIn("max_depth", text)


if __name__ == "__main__":
    unittest.main()
