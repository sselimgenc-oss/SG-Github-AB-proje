"""19 Kasim: sema 1 karsi-olgu deposu (kurulum kolonlari yok) pano/Telegram'da store_io vermemeli."""
import sqlite3

from trader_core import counterfactual as CF


def test_arm_rows_reads_schema1_store(tmp_path):
    p = tmp_path / "counterfactual.sqlite"
    with CF.CounterfactualStore(str(p)) as st:
        pass
    db = sqlite3.connect(p)
    cols = [r[1] for r in db.execute("PRAGMA table_info(cf_outcomes)")]
    keep = [c for c in cols if c not in ("arm_id", "session_tag", "asset_class")]
    db.execute(f"CREATE TABLE t AS SELECT {', '.join(keep)} FROM cf_outcomes")
    db.execute("DROP TABLE cf_outcomes")
    db.execute("ALTER TABLE t RENAME TO cf_outcomes")
    db.execute("PRAGMA user_version=1")
    db.commit(); db.close()
    assert CF.arm_rows(p, "learner") == []
