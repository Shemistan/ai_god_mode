#!/usr/bin/env python3
"""Тесты гейта документации: проверки шапок/связей и пересборка индексов."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import docs_gate  # noqa: E402

SPECS = os.path.join("docs", "superpowers", "specs")
PLANS = os.path.join("docs", "superpowers", "plans")
ADRS = os.path.join("docs", "decisions")


def head(**meta):
    return "---\n" + "".join("%s: %s\n" % kv for kv in meta.items()) + "---\n"


class Repo:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for d in (SPECS, PLANS, ADRS):
            os.makedirs(os.path.join(self.root, d))

    def write(self, rel, text):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def errors(self):
        return [m for _p, m in docs_gate.check(docs_gate.collect(self.root))]


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.tmp.cleanup)

    def spec(self, name="s.md", **meta):
        m = {"тип": "spec", "статус": "черновик", "обновлено": "2026-09-21",
             "план": "нет"}
        m.update(meta)
        self.repo.write(os.path.join(SPECS, name), head(**m) + "# Спека\n")

    def plan(self, name="p.md", **meta):
        m = {"тип": "plan", "статус": "в работе", "обновлено": "2026-09-21",
             "спека": "s.md"}
        m.update(meta)
        self.repo.write(os.path.join(PLANS, name), head(**m) + "# План\n")

    def adr(self, name, **meta):
        m = {"тип": "adr", "статус": "принято", "обновлено": "2026-09-21"}
        m.update(meta)
        self.repo.write(os.path.join(ADRS, name), head(**m) + "# Решение\n")

    def test_ok(self):
        self.spec(план="p.md")
        self.plan()
        self.adr("0001-a.md", статус="заменено", заменён_на="0002-b.md")
        self.adr("0002-b.md")
        self.assertEqual(self.repo.errors(), [])

    def test_readme_not_artifact(self):
        self.repo.write(os.path.join(SPECS, "README.md"), "# индекс\n")
        self.assertEqual(self.repo.errors(), [])

    def test_bad(self):
        cases = [
            (lambda: self.repo.write(os.path.join(SPECS, "x.md"), "# без шапки\n"),
             "нет YAML-шапки"),
            (lambda: self.spec(статус="готово"), "неизвестный статус"),
            (lambda: self.spec(тип="plan"), "не совпадает с папкой"),
            (lambda: self.spec(обновлено="21.09.2026"), "не дата"),
            (lambda: self.spec(план="missing.md"), "не существует"),
            (lambda: (self.spec(план="p.md"), self.plan(спека="other.md")),
             "не существует"),
            (lambda: (self.spec(), self.plan()), "нет обратной ссылки"),
            (lambda: (self.spec(), self.plan(спека="")), "нет обязательного поля 'спека'"),
            (lambda: self.adr("0001-a.md", статус="заменено"), "заменён_на"),
            (lambda: (self.adr("0001-a.md"), self.adr("0001-b.md")), "не уникален"),
            (lambda: self.adr("a.md"), "начинаться с номера"),
        ]
        for make, needle in cases:
            with self.subTest(needle=needle):
                self.repo = Repo()
                self.addCleanup(self.repo.tmp.cleanup)
                make()
                errs = self.repo.errors()
                self.assertTrue(any(needle in e for e in errs), errs)


class TestIndexes(unittest.TestCase):
    def test_regenerate(self):
        repo = Repo()
        self.addCleanup(repo.tmp.cleanup)
        repo.write(os.path.join(SPECS, "s.md"), head(тип="spec", статус="утверждено",
                   обновлено="2026-09-21", план="нет") + "# Спека | один\n")
        repo.write(os.path.join(ADRS, "0001-a.md"), head(тип="adr", статус="принято",
                   обновлено="2026-09-21") + "# Решение А\n")
        readme = os.path.join("docs", "superpowers", "README.md")
        repo.write(readme, "до\n<!-- gate:begin spec-plan-index -->\nстарое\n"
                           "<!-- gate:end spec-plan-index -->\nпосле\n")
        repo.write(os.path.join(ADRS, "README.md"), "без маркеров\n")

        arts = docs_gate.collect(repo.root)
        changed = docs_gate.regenerate(repo.root, arts)

        text = repo.read(readme)
        self.assertEqual(changed, [os.path.join(repo.root, readme)])
        self.assertIn("- [Спека \\| один](specs/s.md) — утверждено", text)
        self.assertIn("### Планы\n\n_пока нет_", text)
        self.assertTrue(text.startswith("до\n") and text.endswith("после\n"))
        self.assertNotIn("старое", text)
        self.assertEqual(repo.read(os.path.join(ADRS, "README.md")), "без маркеров\n")
        self.assertEqual(docs_gate.regenerate(repo.root, arts), [])  # идемпотентно

    def test_adr_table(self):
        a = docs_gate.Artifact("/x/0007-b.md", "adr", {"статус": "принято"}, "# Б\n")
        self.assertIn("| [0007](0007-b.md) | Б | принято |",
                      docs_gate.render_adr_index([a]))


if __name__ == "__main__":
    unittest.main()
