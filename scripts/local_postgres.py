"""Manage an isolated, password-protected PostgreSQL cluster for this workspace."""
import argparse
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from urllib.parse import urlsplit

from dotenv import dotenv_values, set_key
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
CLUSTER = ROOT / "data" / "postgres"
ADMIN_PASSWORD = ROOT / "data" / "postgres-admin-password"
ENV_FILE = ROOT / ".env"
ADMIN = "sre_local_admin"
APP_USER = "agentic_sre"


def binaries():
    configured = os.getenv("PG_BIN")
    if configured:
        return Path(configured)
    executable = shutil.which("initdb")
    if executable:
        return Path(executable).parent
    installed = Path(os.getenv("ProgramFiles", "C:/Program Files")) / "PostgreSQL"
    candidates = sorted(installed.glob("*/bin/initdb.exe"), key=lambda path: int(path.parent.parent.name), reverse=True)
    if not candidates:
        raise RuntimeError("Install PostgreSQL or set PG_BIN to its bin directory.")
    return candidates[0].parent


def run(binary_directory, command, *arguments, check=True):
    executable = binary_directory / (command + (".exe" if os.name == "nt" else ""))
    return subprocess.run([str(executable), *map(str, arguments)], check=check,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def configure_environment(port):
    values = dotenv_values(ENV_FILE)
    url = values.get("DATABASE_URL")
    if url:
        parsed = urlsplit(url)
        if parsed.hostname != "127.0.0.1" or parsed.port != port or parsed.username != APP_USER or parsed.path != "/agentic_sre":
            raise RuntimeError(".env already points to another database; it was left unchanged.")
        password = parsed.password
    else:
        password = secrets.token_urlsafe(32)
        url = f"postgresql://{APP_USER}:{password}@127.0.0.1:{port}/agentic_sre"
        set_key(ENV_FILE, "DATABASE_URL", url)
    if not password:
        raise RuntimeError("The local DATABASE_URL must contain a password.")
    defaults = {
        "POSTGRES_PASSWORD": password,
        "DOCKER_DATABASE_URL": f"postgresql://{APP_USER}:{password}@postgres:5432/agentic_sre",
        "TEST_DATABASE_URL": f"postgresql://{APP_USER}:{password}@127.0.0.1:{port}/agentic_sre_test",
        "SECRET_KEY": secrets.token_urlsafe(48),
        "BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(24),
        "ENVIRONMENT": "development",
    }
    for key, value in defaults.items():
        if not values.get(key):
            set_key(ENV_FILE, key, value)
    return password


def start(binary_directory, port):
    password = configure_environment(port)
    CLUSTER.parent.mkdir(parents=True, exist_ok=True)
    if not (CLUSTER / "PG_VERSION").exists():
        if CLUSTER.exists() and any(CLUSTER.iterdir()):
            raise RuntimeError("The cluster directory is nonempty but not initialized; inspect it before retrying.")
        ADMIN_PASSWORD.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        ADMIN_PASSWORD.chmod(0o600)
        run(binary_directory, "initdb", "-D", CLUSTER, "-U", ADMIN, "--pwfile", ADMIN_PASSWORD,
            "--auth-host=scram-sha-256", "--auth-local=scram-sha-256", "--encoding=UTF8", "--locale=C")
    if not ADMIN_PASSWORD.exists():
        raise RuntimeError("The local cluster administrator password file is missing.")
    if run(binary_directory, "pg_ctl", "-D", CLUSTER, "status", check=False).returncode != 0:
        run(binary_directory, "pg_ctl", "-D", CLUSTER, "-l", CLUSTER.parent / "postgres.log",
            "-o", f"-h 127.0.0.1 -p {port}", "-w", "start")
    with psycopg.connect(host="127.0.0.1", port=port, dbname="postgres", user=ADMIN,
                         password=ADMIN_PASSWORD.read_text(encoding="utf-8"), autocommit=True) as connection:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_USER,)).fetchone():
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(APP_USER), sql.Literal(password)))
        for database in ("agentic_sre", "agentic_sre_test"):
            if not connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,)).fetchone():
                connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(APP_USER)))
    print(f"PostgreSQL ready on 127.0.0.1:{port}; app and test databases created. Credentials are in the ignored .env file.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "stop", "status"], nargs="?", default="start")
    parser.add_argument("--port", type=int, default=55432)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    directory = binaries()
    if args.command == "start":
        start(directory, args.port)
    else:
        run(directory, "pg_ctl", "-D", CLUSTER, *(["-m", "fast", "-w"] if args.command == "stop" else []), args.command)


if __name__ == "__main__":
    main()
