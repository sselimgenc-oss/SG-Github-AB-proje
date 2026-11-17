"""Motor hata sinifleri (02 §3)."""


class EngineError(Exception):
    """Taban."""


class ConfigError(EngineError, ValueError):
    pass


class ClockError(EngineError):
    pass


class DataError(EngineError):
    pass


class StateError(EngineError):
    pass


class BrokerError(EngineError):
    pass


class BrokerUncertain(BrokerError):
    pass


class FailClosed(EngineError):
    pass


class EngineExit(Exception):
    """Surec cikisi (systemd yeniden baslatir). `code` cikis kodu. errors.py'de durur ki brokers/ (engine'i iceri alamaz)
    ayni sinifi firlatabilsin; engine.EngineExit ayni nesnedir."""

    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(message or f"exit {code}")
        self.code = code
