"""Run browser-independent JavaScript route regressions in the standard suite."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_web_route_handlers():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for JavaScript route tests")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("web_routes.test.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
