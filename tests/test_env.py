""".env loader tests — offline. Verifies parsing, comment/quote handling, and that a real
shell env var is NOT overridden by the file (setdefault semantics).

    python -m tests.test_env
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from traingen import env


def test_loads_and_respects_existing_env():
    d = Path(tempfile.mkdtemp())
    (d / ".env").write_text(
        "# a comment\n"
        "\n"
        'TRAINGEN_BASE_URL="http://localhost:3000"\n'
        "TRAINGEN_FPS=24\n"
        "TRAINGEN_ALREADY_SET=from_file\n"
        "ANTHROPIC_API_KEY='sk-quoted'\n",
        encoding="utf-8")

    os.environ.pop("TRAINGEN_BASE_URL", None)
    os.environ.pop("TRAINGEN_FPS", None)
    os.environ["TRAINGEN_ALREADY_SET"] = "from_shell"   # real env must win

    env.load_dotenv(d / ".env")

    assert os.environ["TRAINGEN_BASE_URL"] == "http://localhost:3000", "quotes stripped"
    assert os.environ["TRAINGEN_FPS"] == "24"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-quoted"
    assert os.environ["TRAINGEN_ALREADY_SET"] == "from_shell", "shell env not overridden by .env"
    print("OK  env: parses KEY=VALUE (comments/blanks/quotes), real env wins over the file")


def test_missing_file_is_noop():
    env.load_dotenv(Path(tempfile.mkdtemp()) / "nope.env")   # must not raise
    print("OK  env: missing .env is a no-op")


def test_config_reads_env(monkeypatch=None):
    from traingen import config
    os.environ["TRAINGEN_FPS"] = "48"
    os.environ["TRAINGEN_VIEWPORT"] = "1280x720"
    os.environ["TRAINGEN_TTS"] = "omnivoice"
    os.environ["TRAINGEN_HEADLESS"] = "1"
    os.environ["TRAINGEN_BROWSER_ARGS"] = "--disable-gpu, --disable-dev-shm-usage"
    cfg = config.load_config()
    assert cfg.fps == 48 and cfg.viewport == {"width": 1280, "height": 720}
    assert cfg.tts_backend == "omnivoice" and cfg.headless is True
    assert cfg.browser_args == ["--disable-gpu", "--disable-dev-shm-usage"]
    for k in ("TRAINGEN_FPS", "TRAINGEN_VIEWPORT", "TRAINGEN_TTS", "TRAINGEN_HEADLESS", "TRAINGEN_BROWSER_ARGS"):
        os.environ.pop(k, None)
    print("OK  config: load_config honours TRAINGEN_* (fps, viewport, tts, headless, browser_args)")


def main() -> int:
    test_loads_and_respects_existing_env()
    test_missing_file_is_noop()
    test_config_reads_env()
    print("\nall env tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
