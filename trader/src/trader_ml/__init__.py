"""ML fazi egitim hatti (ML-0c, tasarim: otonom-trading-arastirma/ml-faz-tasarimi.md v2).

Motordan (trader_engine) ve cekirdekten (trader_core) AYRI paket. Egitim/arastirma tarafi
lightgbm kullanabilir (yalniz bu pakette, `requirements-ml.txt`); `treeeval` ise yalniz numpy'a
baglidir ve motor tarafinda lightgbm'siz model calistirir. Kilitli donem (2026-05 -> 2026-10)
hicbir kod yolunda okunmaz (`guards`).
"""
