"""Sentetik data.binance.vision fixture uretici (deterministik; ag yok). Cikti: tests/fixtures/vision/<URL yolu>.
Yeniden uretmek icin: python tests/fixtures/make_vision_fixtures.py  (committed dosyalarin ayni baytlari uretmesi beklenir)."""
from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent / "vision" / "monthly"
HDR = "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore"


def ms(y, m, d, h=0):
    return int(datetime(y, m, d, h, tzinfo=timezone.utc).timestamp() * 1000)


def make_zip(name: str, csv: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        zi = zipfile.ZipInfo(name + ".csv", date_time=(2021, 1, 1, 0, 0, 0))  # sabit damga -> deterministik bayt
        z.writestr(zi, csv)
    return buf.getvalue()


def kline_csv(y, m, ndays, base, header=True, hours=1, skip_days=()):
    rows = [HDR] if header else []
    for d in range(1, ndays + 1):
        if d in skip_days:
            continue
        for h in range(0, 24, hours):
            t = ms(y, m, d, h)
            p = base + d + h / 100
            rows.append(f"{t},{p},{p + 1},{p - 1},{p + 0.5},{10 + h},{t + 3599999},0,0,0,0,0")
    return "\n".join(rows) + "\n"


def funding_csv(y, m, ndays, base):
    rows = ["calc_time,funding_interval_hours,last_funding_rate"]
    for d in range(1, ndays + 1):
        for h in (0, 8, 16):
            rows.append(f"{ms(y, m, d, h) + 5},8,{base + d * 1e-6 + h * 1e-8:.8f}")
    return "\n".join(rows) + "\n"


def put(rel: str, blob: bytes, checksum: str | None = "ok") -> None:
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(blob)
    if checksum:
        digest = hashlib.sha256(blob).hexdigest() if checksum == "ok" else "0" * 64
        Path(str(p) + ".CHECKSUM").write_text(f"{digest}  {p.name}\n")


def main() -> None:
    put("klines/BTCUSDT/1h/BTCUSDT-1h-2021-01.zip", make_zip("BTCUSDT-1h-2021-01", kline_csv(2021, 1, 31, 1000)))
    put("klines/BTCUSDT/1h/BTCUSDT-1h-2021-02.zip", make_zip("BTCUSDT-1h-2021-02", kline_csv(2021, 2, 28, 2000, header=False)))
    put("markPriceKlines/BTCUSDT/1h/BTCUSDT-1h-2021-01.zip", make_zip("BTCUSDT-1h-2021-01", kline_csv(2021, 1, 31, 1001)))
    put("fundingRate/BTCUSDT/BTCUSDT-fundingRate-2021-01.zip", make_zip("BTCUSDT-fundingRate-2021-01", funding_csv(2021, 1, 31, 1e-4)))
    # sahte (bozuk) sagalama toplami: reddedilmeli
    put("klines/ETHUSDT/1h/ETHUSDT-1h-2021-01.zip", make_zip("ETHUSDT-1h-2021-01", kline_csv(2021, 1, 31, 300)), checksum="bad")
    # .CHECKSUM hic yok
    put("klines/XRPUSDT/1h/XRPUSDT-1h-2021-01.zip", make_zip("XRPUSDT-1h-2021-01", kline_csv(2021, 1, 31, 1)), checksum=None)


if __name__ == "__main__":
    main()
