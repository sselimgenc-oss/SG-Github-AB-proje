"""YER TUTUCU STRATEJI - GERCEK STRATEJI DEGILDIR.

Hicbir zaman giris sinyali uretmez; bot islem acmaz. Altyapiyi (config, docker,
API) dogrulamak icin vardir. Gercek strateji sonraki asamada eklenecek.
"""
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class PlaceholderStrategy(IStrategy):
    INTERFACE_VERSION = 3

    can_short = True
    timeframe = "1h"
    startup_candle_count = 0

    # Yer tutucu: cikis kurallari anlamsiz, giris zaten yok.
    minimal_roi = {"0": 100}
    stoploss = -0.99
    process_only_new_candles = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Sinyal yok: enter_long / enter_short hic set edilmez.
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe
