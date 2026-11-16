"""Panel kaynak taramasi: sir/ortam yok, ag yok, yazma yok, trader_engine/telegram ice aktarma yok, sabit esik yok."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted((ROOT / "src/trader_panel").glob("*.py")) + [ROOT / "src/trader_core/panel_data.py"]


def code(p: Path) -> str:
    return re.sub(r"(?m)^\s*#.*$", "", p.read_text(encoding="utf-8"))


def test_files_present():
    assert {p.name for p in FILES} >= {"server.py", "data.py", "__main__.py", "panel_data.py"}


def test_no_secret_or_environment_access():
    for p in FILES:
        t = code(p)
        assert not re.search(r"os\.environ|getenv|\benviron\b", t), p.name
        assert not re.search(r"TELEGRAM_|ANTHROPIC|_API_KEY|_TOKEN|HMAC|EnvironmentFile", t), p.name


def test_no_engine_or_telegram_import_no_network_client():
    for p in FILES:
        t = code(p)
        assert not re.search(r"(?m)^\s*(from|import)\s+(trader_engine|trader_core\.telegram)\b", t), p.name
        assert not re.search(r"(?m)^\s*from\s+(\.|trader_core)\s*import\s+.*\btelegram\b", t), p.name
        assert not re.search(r"\b(requests|urllib\.request|http\.client|socket\.create_connection|smtplib|websockets)\b", t), p.name


def test_no_writes_to_data():
    for p in FILES:
        t = code(p)
        assert not re.search(r"write_text|write_bytes|os\.(remove|unlink|rename|replace|makedirs|mkdir)|shutil\.|"
                             r"open\([^)]*(,\s*|mode=)['\"][wax+]", t), p.name
        assert "record_" not in t and "init_params" not in t and "authorize" not in t, p.name


def test_no_literal_thresholds():
    for p in FILES:
        t = code(p)
        for ln in t.splitlines():
            if ln.startswith("STALE_S = "):          # tek tanim (telegram ile esitligi testle sinanir)
                continue
            assert not re.search(r"(?<![\w.])0\.05(?![\w])|(?<![\w.])120(?![\w.])", ln), (p.name, ln)
