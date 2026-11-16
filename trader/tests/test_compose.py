from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
services = compose["services"]


def test_services_present():
    assert {"learner", "twin"} <= set(services)


def test_ports_bound_to_localhost_and_distinct():
    hosts = []
    for svc in services.values():
        for p in svc["ports"]:
            assert p.startswith("127.0.0.1:"), p
            hosts.append(p.split(":")[1])
    assert len(hosts) == len(set(hosts))


def _userdata(svc):
    return [v.split(":")[0] for v in svc["volumes"] if v.endswith(":/freqtrade/user_data")]


def test_separate_user_data_volumes():
    l, t = _userdata(services["learner"]), _userdata(services["twin"])
    assert len(l) == 1 and len(t) == 1 and l != t


def test_shared_mount_read_only_and_restart():
    for svc in services.values():
        assert "./shared:/freqtrade/shared:ro" in svc["volumes"]
        assert svc["restart"] == "unless-stopped"
        assert "max-size" in svc["logging"]["options"]


def test_trader_core_importable_in_container():
    # Strateji `trader_core`'u iceri aktarir: src salt-okunur baglanir, PYTHONPATH ona isaret eder.
    for svc in services.values():
        assert "./src:/freqtrade/trader_src:ro" in svc["volumes"]
        assert "PYTHONPATH=/freqtrade/trader_src" in svc["environment"]
