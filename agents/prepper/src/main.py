"""Agent 1 — Prepper
Setup wizard that captures DB + LM Studio config, renders docker-compose.yml
and .env from templates, then starts the other agents and exits.
"""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(title="SLR Pipeline — Prepper", version="1.0.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Path where Prepper can write files (mounted from host)
APP_DIR = Path("/app")
ENV_FILE = APP_DIR / ".env"
COMPOSE_FILE = APP_DIR / "docker-compose.yml"


class SetupForm(BaseModel):
    pghost: str
    pgport: int = 5432
    pguser: str
    pgpassword: str
    pgdatabase: str
    pgssl: bool = True
    lm_studio_url: str = "http://host.docker.internal:1234/v1"
    lm_studio_model: str = "local-model"
    data_dir: str = "/data"


@app.get("/", response_class=HTMLResponse)
async def wizard_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("wizard.html", {"request": request})


@app.post("/setup")
async def run_setup(
    request: Request,
    pghost: str = Form(...),
    pgport: int = Form(5432),
    pguser: str = Form(...),
    pgpassword: str = Form(...),
    pgdatabase: str = Form(...),
    pgssl: str = Form("true"),
    lm_studio_url: str = Form("http://host.docker.internal:1234/v1"),
    lm_studio_model: str = Form("local-model"),
    data_dir: str = Form("/data"),
) -> JSONResponse:
    config = SetupForm(
        pghost=pghost,
        pgport=pgport,
        pguser=pguser,
        pgpassword=pgpassword,
        pgdatabase=pgdatabase,
        pgssl=pgssl.lower() in ("true", "1", "yes"),
        lm_studio_url=lm_studio_url,
        lm_studio_model=lm_studio_model,
        data_dir=data_dir,
    )

    _write_env(config)
    _write_compose(config)

    # Spin up remaining agents
    try:
        subprocess.Popen(
            ["docker", "compose", "up", "-d", "dio", "mel", "simo"],
            cwd=str(APP_DIR),
        )
    except FileNotFoundError:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "docker compose not found in container"},
        )

    # Schedule self-termination after response is sent
    def _shutdown() -> None:
        os.kill(os.getpid(), signal.SIGTERM)

    import threading
    threading.Timer(2.0, _shutdown).start()

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "message": "Pipeline started. Prepper will exit shortly.",
            "agents": {
                "DIO": "http://localhost:7001",
                "MEL": "http://localhost:7002",
                "SIMO": "http://localhost:7003",
            },
        },
    )


def _write_env(cfg: SetupForm) -> None:
    """Render and persist .env from template values."""
    content = (
        f"PGHOST={cfg.pghost}\n"
        f"PGPORT={cfg.pgport}\n"
        f"PGUSER={cfg.pguser}\n"
        f"PGPASSWORD={cfg.pgpassword}\n"
        f"PGDATABASE={cfg.pgdatabase}\n"
        f"PGSSL={'true' if cfg.pgssl else 'false'}\n"
        f"LM_STUDIO_URL={cfg.lm_studio_url}\n"
        f"LM_STUDIO_MODEL={cfg.lm_studio_model}\n"
        f"ARTIFACTS_DIR=/artifacts\n"
        f"DATA_DIR={cfg.data_dir}\n"
        f"CHROMA_PERSIST_DIR=/artifacts/chroma\n"
        f"PREPPER_PORT=7000\n"
        f"DIO_PORT=7001\n"
        f"MEL_PORT=7002\n"
        f"SIMO_PORT=7003\n"
    )
    ENV_FILE.write_text(content)


def _write_compose(cfg: SetupForm) -> None:
    """Re-render docker-compose.yml with correct data_dir bind mount for MEL."""
    template = templates.get_template("docker-compose.yml.j2")
    rendered = template.render(data_dir=cfg.data_dir)
    COMPOSE_FILE.write_text(rendered)
