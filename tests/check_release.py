"""Check release metadata and the actual installed, locked environment."""
import ast
import importlib.metadata
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
version = importlib.metadata.version("neurodynamic-mcp")
for filename in ("pyproject.toml", "setup.py", "neurodynamic_mcp/__init__.py", "neurodynamic_mcp/server.py"):
    text = (ROOT / filename).read_text()
    match = re.search(r"(?:__version__|version)\s*=\s*['\"]([^'\"]+)['\"]", text)
    assert match and match[1] == version, (filename, version)
manifest = json.loads((ROOT / "server.json").read_text())
assert manifest["version"] == version
assert all(p["version"] == version for p in manifest["packages"])
assert f"NeuroDynamic-MCP/{version}" in (ROOT / "neurodynamic_mcp/client_core.py").read_text()
assert f"neurodynamic-mcp=={version}" in (ROOT / "README.md").read_text()
tag = os.environ.get("GITHUB_REF", "")
if tag.startswith("refs/tags/"):
    assert tag == f"refs/tags/v{version}", tag
for line in (ROOT / "requirements.lock").read_text().splitlines():
    if line.strip() and not line.startswith("#"):
        name, pinned = line.split("==")
        installed = importlib.metadata.version(name)
        assert installed == pinned, (name, pinned, installed)
# Keep legacy setup metadata consistent with the canonical pyproject.
setup = ast.parse((ROOT / "setup.py").read_text())
requires = next(ast.literal_eval(k.value) for n in ast.walk(setup)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "setup"
                for k in n.keywords if k.arg == "install_requires")
project_line = next(x for x in (ROOT / "pyproject.toml").read_text().splitlines() if x.startswith("dependencies ="))
assert requires == ast.literal_eval(project_line.split("=", 1)[1].strip())
print(f"Release {version}: metadata, tag (when present), and installed lock match")
