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
