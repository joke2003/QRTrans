import subprocess
import sys

def test_cli_runs():
    result = subprocess.run(
        [sys.executable, "-m", "qrtrans"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
