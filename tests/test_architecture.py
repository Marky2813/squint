import ast
from pathlib import Path

CORE = Path(__file__).parent.parent / "src" / "squint" / "core"


def test_core_never_imports_platforms():
    for path in CORE.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not name.startswith("squint.platforms"), f"{path} imports {name}"
