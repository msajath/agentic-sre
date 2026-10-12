"""Run the Postman collection on a new disposable local PostgreSQL database."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

from dotenv import dotenv_values
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
POSTMAN = ROOT / "postman"
PORT = 8001


def command(*parts, env, stdout=None):
    return subprocess.run(parts, cwd=ROOT, env=env, stdout=stdout, stderr=subprocess.STDOUT,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, check=True)


def main():
    config = dotenv_values(ROOT / ".env")
    source_url = config.get("DATABASE_URL")
    if not source_url:
        raise RuntimeError("Configure DATABASE_URL in the project .env before local API tests.")
    source = make_url(source_url)
    if source.host != "127.0.0.1" or source.port != 55432 or source.database != "agentic_sre":
        raise RuntimeError("The isolated Postman runner requires the workspace's local PostgreSQL cluster.")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            raise RuntimeError(f"Port {PORT} is already in use; stop that service before running isolated API tests.")
    admin_password_file = DATA / "postgres-admin-password"
    if not admin_password_file.is_file():
        raise RuntimeError("Start scripts/local_postgres.py before running the Postman collection.")

    database = "agentic_sre_postman_" + secrets.token_hex(4) + "_test"
    app_url = source.set(database=database).render_as_string(hide_password=False)
    admin_password = admin_password_file.read_text(encoding="utf-8")
    credentials = {role: secrets.token_urlsafe(24) for role in ("admin", "operator", "viewer")}
    env = {**os.environ, "DATABASE_URL": app_url, "SIMULATION_ENABLED": "true", "ENVIRONMENT": "test",
           "SECRET_KEY": secrets.token_urlsafe(48), "BOOTSTRAP_ADMIN_PASSWORD": credentials["admin"]}
    npm = "C:/Program Files/nodejs/npm.cmd" if os.name == "nt" else "npm"
    node = "C:/Program Files/nodejs/node.exe" if os.name == "nt" else "node"
    newman = DATA / "postman-runner" / "node_modules" / "newman" / "bin" / "newman.js"
    report_path = DATA / "postman-newman-results.json"
    environment_path = DATA / "postman-run-environment.json"
    server = None
    created = False
    DATA.mkdir(exist_ok=True)
    try:
        if not newman.is_file():
            command(npm, "install", "--prefix", str(DATA / "postman-runner"), "newman@6.2.3",
                    "--prefer-offline", "--no-audit", env=env, stdout=subprocess.DEVNULL)
        with psycopg.connect(host=source.host, port=source.port, dbname="postgres", user="sre_local_admin",
                             password=admin_password, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(source.username)))
        created = True
        command(npm, "run", "db:migrate", env=env, stdout=subprocess.DEVNULL)
        provision = """from src.database import init_db
from src.services.auth_service import auth_service
from src.models.auth import UserRole
import os
init_db()
for role in ('admin','operator','viewer'):
    auth_service.provision_user(role, os.environ['POSTMAN_'+role.upper()+'_PASSWORD'], getattr(UserRole,role.upper()))
"""
        child_env = {**env, **{f"POSTMAN_{role.upper()}_PASSWORD": password for role, password in credentials.items()}}
        command(sys.executable, "-c", provision, env=child_env, stdout=subprocess.DEVNULL)
        template = json.loads((POSTMAN / "isolated.postman_environment.json").read_text(encoding="utf-8"))
        for variable in template["values"]:
            for role, password in credentials.items():
                if variable["key"] == f"{role}Password":
                    variable["value"] = password
        environment_path.write_text(json.dumps(template), encoding="utf-8")
        environment_path.chmod(0o600)
        with (DATA / "postman-uvicorn.log").open("w", encoding="utf-8") as server_log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "src.main:app", "--host", "127.0.0.1",
                                       "--port", str(PORT), "--workers", "1"], cwd=ROOT, env=env,
                                      stdout=server_log, stderr=subprocess.STDOUT,
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            for _ in range(50):
                if server.poll() is not None:
                    raise RuntimeError("Postman test API failed to start; inspect data/postman-uvicorn.log.")
                try:
                    with urlopen(f"http://127.0.0.1:{PORT}/readyz", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Postman test API did not become ready in time.")
            with (DATA / "postman-newman.log").open("w", encoding="utf-8") as newman_log:
                result = subprocess.run([node, str(newman), "run",
                                         str(POSTMAN / "agentic-sre.postman_collection.json"), "-e", str(environment_path),
                                         "--reporters", "json", "--reporter-json-export", str(report_path),
                                         "--timeout-request", "120000"], cwd=ROOT, env=env,
                                        stdout=newman_log, stderr=subprocess.STDOUT,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if not report_path.exists():
            raise RuntimeError("Newman did not produce a report; inspect data/postman-newman.log.")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        stats = report.get("run", {}).get("stats", {})
        failures = report.get("run", {}).get("failures", [])
        summary = {"requests": stats.get("requests", {}).get("total"),
                   "assertions": stats.get("assertions", {}).get("total"),
                   "failed_assertions": stats.get("assertions", {}).get("failed"),
                   "failure_count": len(failures),
                   "failed_request_names": sorted({failure.get("source", {}).get("name", "unknown") for failure in failures})}
        (DATA / "postman-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        if result.returncode or failures:
            raise RuntimeError("Postman tests failed; inspect the ignored data/postman-newman-results.json report.")
        report_path.unlink()
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            server.wait(timeout=10)
        environment_path.unlink(missing_ok=True)
        if created:
            with psycopg.connect(host=source.host, port=source.port, dbname="postgres", user="sre_local_admin",
                                 password=admin_password, autocommit=True) as admin:
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))


if __name__ == "__main__":
    main()
