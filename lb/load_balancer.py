import os
import re
import subprocess
import httpx
from pathlib import Path
from typing import Dict, List, Optional

NGINX_DIR = Path(__file__).resolve().parent / "nginx"
NGINX_EXE = NGINX_DIR / "nginx.exe"
NGINX_CONF = NGINX_DIR / "conf" / "nginx.conf"
CONF_SOURCE = Path(__file__).resolve().parent / "nginx.conf"

UPSTREAM_TEMPLATE = """    upstream llm_backend {{
{strategy_line}
{server_lines}
    }}"""


class LoadBalancer:

    def __init__(self):
        self._ensure_running()

    def _ensure_running(self):
        if not NGINX_EXE.exists():
            raise RuntimeError(
                "NGINX not found. Run setup.ps1 first or place nginx.exe in lb/nginx/"
            )
        if not NGINX_CONF.exists():
            self._deploy_config()
        result = subprocess.run(
            [str(NGINX_EXE), "-p", str(NGINX_DIR), "-t"], capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"NGINX config test failed:\n{result.stderr}")

    def _deploy_config(self):
        NGINX_CONF.parent.mkdir(parents=True, exist_ok=True)
        with open(CONF_SOURCE) as f:
            config = f.read()
        with open(NGINX_CONF, "w") as f:
            f.write(config)

    def reload(self):
        subprocess.run([str(NGINX_EXE), "-p", str(NGINX_DIR), "-s", "reload"], check=True)

    def disable_worker(self, worker_id: str):
        port = self._worker_id_to_port(worker_id)
        self._update_server_line(port, comment=True)

    def enable_worker(self, worker_id: str):
        port = self._worker_id_to_port(worker_id)
        self._update_server_line(port, comment=False)

    def add_worker(self, worker_id: str, host: str = "localhost"):
        port = self._worker_id_to_port(worker_id)
        line = f"        server {host}:{port} max_fails=3 fail_timeout=30s;"
        with open(NGINX_CONF) as f:
            content = f.read()
        if line.strip(" ") in content:
            return
        insert_pos = content.rfind("    }")
        if insert_pos == -1:
            raise RuntimeError("Could not find upstream block end in nginx.conf")
        content = content[:insert_pos] + line + "\n" + content[insert_pos:]
        with open(NGINX_CONF, "w") as f:
            f.write(content)
        self.reload()

    def remove_worker(self, worker_id: str):
        port = self._worker_id_to_port(worker_id)
        line_pattern = rf"^\s*server\s+localhost:{port}\s+.*$"
        with open(NGINX_CONF) as f:
            content = f.read()
        content = re.sub(line_pattern, "", content, flags=re.MULTILINE)
        content = re.sub(r"\n{3,}", "\n\n", content)
        with open(NGINX_CONF, "w") as f:
            f.write(content)
        self.reload()

    def switch_strategy(self, strategy: str):
        if strategy == "round_robin":
            replacement = "        # least_conn;"
        elif strategy == "least_connections":
            replacement = "        least_conn;"
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
        with open(NGINX_CONF) as f:
            content = f.read()
        content = re.sub(
            r"\s*#?\s*least_conn;", f"\n{replacement}", content
        )
        with open(NGINX_CONF, "w") as f:
            f.write(content)
        self.reload()

    def get_status(self) -> dict:
        try:
            resp = httpx.get("http://localhost:8000/nginx_status", timeout=5.0)
            return self._parse_status(resp.text)
        except Exception:
            return {"error": "could not reach NGINX status page"}

    def get_worker_list(self) -> List[dict]:
        workers = []
        with open(NGINX_CONF) as f:
            for line in f:
                match = re.search(r"server\s+localhost:(\d+)", line)
                if match:
                    port = int(match.group(1))
                    worker_id = f"worker-{port - 8000}"
                    disabled = line.strip().startswith("#")
                    workers.append({
                        "worker_id": worker_id,
                        "port": port,
                        "enabled": not disabled,
                    })
        return workers

    def get_current_strategy(self) -> str:
        with open(NGINX_CONF) as f:
            for line in f:
                stripped = line.strip()
                if stripped == "least_conn;":
                    return "least_connections"
        return "round_robin"

    def _update_server_line(self, port: int, comment: bool):
        with open(NGINX_CONF) as f:
            content = f.read()
        pattern = rf"^\s*#?\s*server localhost:{port}\s+.*$"
        replacement = f"        server localhost:{port} max_fails=3 fail_timeout=30s;"
        if comment:
            replacement = f"        # {replacement.strip()}"
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        with open(NGINX_CONF, "w") as f:
            f.write(content)
        self.reload()

    def _worker_id_to_port(self, worker_id: str) -> int:
        match = re.search(r"(\d+)", worker_id)
        if not match:
            raise ValueError(f"Invalid worker_id format: {worker_id}")
        return 8000 + int(match.group(1))

    def _parse_status(self, raw: str) -> dict:
        result = {}
        for line in raw.strip().split("\n"):
            if "Active connections:" in line:
                result["active_connections"] = int(line.split(":")[1].strip())
            elif "server" in line and "requests" in line:
                parts = line.strip().split()
                if len(parts) >= 3:
                    result["total_requests"] = int(parts[1])
        return result
