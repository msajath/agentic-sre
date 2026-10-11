"""Run backend checks only against a dedicated PostgreSQL test database."""
import os
from pathlib import Path
import subprocess
import sys
from dotenv import dotenv_values

def main():
    root = Path(__file__).resolve().parent.parent
    test_url = os.getenv("TEST_DATABASE_URL") or dotenv_values(root / ".env").get("TEST_DATABASE_URL")
    if not test_url:
        raise RuntimeError("Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending in _test.")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", *sys.argv[1:]], cwd=root,
                            env={**os.environ, "TEST_DATABASE_URL": test_url})
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
