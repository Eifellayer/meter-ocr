"""Every local module the app imports must be copied into the image (0.5.27).

0.5.25 imported a new module that the Dockerfile did not copy: the tests ran from the source
folder and passed, the installed app did not start. This test follows the imports from run.py
like the image does and fails for any local module missing from the COPY line.
"""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def copied_files():
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    files = set()
    for line in docker.splitlines():
        if line.startswith("COPY "):
            files.update(line.split()[1:-1])
    return files


def local_imports(module):
    tree = ast.parse((ROOT / f"{module}.py").read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return {name for name in names if (ROOT / f"{name}.py").is_file()}


class ImageContentsTest(unittest.TestCase):
    def test_every_imported_local_module_is_in_the_image(self):
        seen, todo = set(), ["run"]
        while todo:
            module = todo.pop()
            if module in seen:
                continue
            seen.add(module)
            todo.extend(local_imports(module) - seen)
        missing = sorted(f"{module}.py" for module in seen if f"{module}.py" not in copied_files())
        self.assertEqual([], missing, "modules imported by the app but not copied by the Dockerfile")

    def test_copy_line_names_only_existing_files(self):
        for name in copied_files():
            with self.subTest(file=name):
                self.assertTrue((ROOT / name).exists(), name)
        self.assertTrue(re.search(r"\bkit_camera\.py\b", (ROOT / "Dockerfile").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
