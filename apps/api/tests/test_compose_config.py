"""Check Compose against synthetic configuration only, never the local credential file."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[3]


def test_only_api_loads_backend_env_file_and_provider_is_not_interpolated():
    services = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    assert services["api"]["env_file"] == ["./apps/api/.env"]
    assert all(not entry.startswith("AGENT_PROVIDER") for entry in services["api"]["environment"])
    assert "env_file" not in services["web"]
    assert all(
        not any(key in entry for key in ("GROQ_API_KEY", "TMDB_API_KEY", "GOOGLE_BOOKS_API_KEY"))
        for entry in services["web"]["environment"]
    )
    override = yaml.safe_load((ROOT / "docker-compose.mock.yml").read_text(encoding="utf-8"))
    assert override["services"]["api"]["environment"]["AGENT_PROVIDER"] == "mock"


def test_settings_loads_provider_from_synthetic_file_and_allows_explicit_override(
    tmp_path, monkeypatch
):
    config = tmp_path / "synthetic.env"
    config.write_text("AGENT_PROVIDER=groq\n", encoding="utf-8")
    assert Settings(_env_file=config).agent_provider == "groq"
    monkeypatch.setenv("AGENT_PROVIDER", "mock")
    assert Settings(_env_file=config).agent_provider == "mock"


@pytest.mark.parametrize("host_provider", ["mock", "groq"])
@pytest.mark.parametrize("use_mock_override", [False, True])
def test_real_compose_resolution_ignores_host_provider(tmp_path, host_provider, use_mock_override):
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker CLI unavailable; static configuration checks still run")
    backend = tmp_path / "apps" / "api"
    backend.mkdir(parents=True)
    (backend / ".env").write_text(
        "AGENT_PROVIDER=groq\nGROQ_API_KEY='synthetic-test-key'\n"
        "TMDB_API_KEY=synthetic-tmdb\nGOOGLE_BOOKS_API_KEY=synthetic-books\n",
        encoding="utf-8",
    )
    compose = tmp_path / "docker-compose.yml"
    compose.write_text((ROOT / "docker-compose.yml").read_text(encoding="utf-8"), encoding="utf-8")
    empty = tmp_path / "empty.env"
    empty.write_text("", encoding="utf-8")
    docker_config = tmp_path / "docker-config"
    docker_config.mkdir()
    env = {key: value for key, value in os.environ.items() if not key.startswith("COMPOSE_")}
    env.update(AGENT_PROVIDER=host_provider, DOCKER_CONFIG=str(docker_config))
    command = [docker, "compose", "--env-file", str(empty), "-f", str(compose)]
    if use_mock_override:
        command.extend(["-f", str(ROOT / "docker-compose.mock.yml")])
    command.extend(["config", "--format", "json"])
    result = subprocess.run(
        command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30, check=False
    )
    if result.returncode and "not a docker command" in result.stderr:
        pytest.skip("Compose plugin unavailable")
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    api = services["api"]["environment"]
    assert api["AGENT_PROVIDER"] == ("mock" if use_mock_override else "groq")
    assert api["GROQ_API_KEY"] == "synthetic-test-key"
    assert (
        not {"GROQ_API_KEY", "TMDB_API_KEY", "GOOGLE_BOOKS_API_KEY"}
        & services["web"]["environment"].keys()
    )
