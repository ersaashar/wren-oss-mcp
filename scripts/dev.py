"""Initialize and serve the local Jaffle MCP project."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "projects" / "jaffle-wren"
HOME = ROOT / ".wren" / "host"


def main() -> int:
    os.chdir(ROOT)
    env_file = dotenv_values(ROOT / ".env.dev")
    port = os.environ.get("WREN_PORT") or env_file.get("WREN_PORT") or "8080"
    os.environ.update(
        PYTHONUTF8="1",
        WREN_HOME=str(HOME),
        WREN_MEMORY_BACKEND="lancedb",
        WREN_EMBEDDING_BACKEND="onnx",
        WREN_EMBEDDING_MODEL="paraphrase-multilingual-MiniLM-L12-v2",
    )
    HOME.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "config" / "wren-config.json", HOME / "config.json")
    profile = {
        "active": "jaffle-host",
        "profiles": {
            "jaffle-host": {
                "datasource": "duckdb",
                "url": str(ROOT / "data"),
                "format": "duckdb",
            }
        },
    }
    (HOME / "profiles.yml").write_text(yaml.safe_dump(profile), encoding="utf-8")
    wren = str(Path(sys.executable).parent / ("wren.exe" if os.name == "nt" else "wren"))
    subprocess.run([wren, "context", "validate", "--path", str(PROJECT)], check=True)
    subprocess.run([wren, "context", "build", "--path", str(PROJECT)], check=True)
    sys.path.insert(0, str(ROOT / "docker"))
    from initialize_memory import initialize_memory

    initialize_memory(PROJECT)
    return subprocess.run(
        [
            wren, "serve", "mcp", "--project", str(PROJECT), "--profile", "jaffle-host",
            "--transport", "http", "--host", "127.0.0.1", "--port", port,
        ],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
