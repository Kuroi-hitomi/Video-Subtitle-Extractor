"""Choose a verified runtime without changing any earlier environment."""
import json
import os
from pathlib import Path
import tempfile

APP = Path(__file__).resolve().parent
CONFIG_NAME = "runtime.json"


def contained_path(relative, app=None):
    app = Path(app or APP).resolve()
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("Runtime configuration must contain a relative path")
    result = (app / relative).resolve()
    if not result.is_relative_to(app) or result == app:
        raise ValueError("Runtime path must remain inside the application folder")
    return result


def read_config(app=None):
    app = Path(app or APP).resolve()
    config = app / CONFIG_NAME
    if not config.is_file():
        return None
    value = json.loads(config.read_text(encoding="utf-8"))
    if value.get("version") != 1:
        raise ValueError("Unsupported runtime configuration; restore the correct runtime.json")
    environment = contained_path(value["environment"], app)
    models = contained_path(value["speaker_models"], app)
    if not models.is_relative_to(environment):
        raise ValueError("Speaker cache must belong to the selected runtime")
    return environment, models


def active_environment(app=None):
    app = Path(app or APP).resolve()
    configured = read_config(app)
    return configured[0] if configured else app / ".venv"


def speaker_model_root():
    # Only the repair subprocess receives this override, before activation.
    override = os.environ.get("VIDEO_SUBTITLE_SPEAKER_MODELS")
    if override:
        return contained_path(override)
    configured = read_config()
    return configured[1] if configured else APP / "models" / "speakers"


def activate(environment, models, app=None):
    app = Path(app or APP).resolve()
    environment, models = Path(environment).resolve(), Path(models).resolve()
    value = {"version": 1, "environment": environment.relative_to(app).as_posix(),
             "speaker_models": models.relative_to(app).as_posix()}
    if not models.is_relative_to(environment):
        raise ValueError("Speaker cache must belong to the selected runtime")
    if not (environment / "Scripts" / "python.exe").is_file():
        raise ValueError("Candidate Python is missing")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=app,
                                     prefix="runtime-", suffix=".tmp", delete=False) as output:
        staged = Path(output.name)
        json.dump(value, output, indent=2)
    try:
        os.replace(staged, app / CONFIG_NAME)
    finally:
        staged.unlink(missing_ok=True)


def clean_environment():
    value = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "VIDEO_SUBTITLE_SPEAKER_MODELS",
                "PIP_TARGET", "PIP_PREFIX", "PIP_USER"):
        value.pop(key, None)
    value["PYTHONNOUSERSITE"] = "1"
    return value
