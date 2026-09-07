#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import commit_msg  # noqa: E402

VALID = [
    "feat: добавить guard",
    "fix(guard): регекс force-push",
    "docs: обновить README",
    "chore!: breaking-изменение",
    "Merge branch 'worktree-x'",
    "Revert \"feat: сломанное\"",
    "fixup! feat: добавить guard",
]

INVALID = [
    "добавил фичу",                          # нет типа
    "feature: x",                            # неизвестный тип
    "feat добавить",                         # нет двоеточия
    "feat: " + "x" * 80,                     # сабж >72
    "feat: x\n\nCo-Authored-By: Claude <a@b>",   # соавторство
    "feat: x\n\nGenerated with Claude Code",     # соавторство
]


class TestValidate(unittest.TestCase):
    def test_valid(self):
        for msg in VALID:
            with self.subTest(msg=msg):
                self.assertEqual(commit_msg.validate(msg), [], msg)

    def test_invalid(self):
        for msg in INVALID:
            with self.subTest(msg=msg):
                self.assertNotEqual(commit_msg.validate(msg), [], msg)


if __name__ == "__main__":
    unittest.main()
