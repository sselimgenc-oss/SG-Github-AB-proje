"""DD-12 WP-14: M1 (ML'in kendi adayi) - fiyat-hareketi ozelliklerinden tek-yonlu (long/short) lojistik model.

Yalniz numpy (+ stdlib, trader_core.ml_package/ml_eval). Ozellik ve etiket kodu hem egitimde (research/pa_proposer_build.py)
hem canli kolda (strategies/arms/m1.py) AYNI fonksiyonlardir (`features.feature_vector`): parite bit-bit.
"""
from __future__ import annotations
