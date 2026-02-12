"""Custom exception hierarchy for the copy trading system"""


class CopyTradingError(Exception):
    """Base exception for all copy trading errors"""
    pass


class ExchangeError(CopyTradingError):
    """Base exception for exchange-related errors"""
    pass


class ConnectionError(ExchangeError):
    """Connection to exchange failed"""
    pass


class AuthenticationError(ExchangeError):
    """Authentication with exchange failed"""
    pass


class RateLimitError(ExchangeError):
    """Rate limit exceeded"""
    pass


class APIError(ExchangeError):
    """Generic API error from exchange"""
    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class PositionError(CopyTradingError):
    """Base exception for position-related errors"""
    pass


class PositionNotFoundError(PositionError):
    """Position not found"""
    pass


class InsufficientBalanceError(PositionError):
    """Insufficient balance for operation"""
    pass


class OrderError(CopyTradingError):
    """Base exception for order-related errors"""
    pass


class OrderExecutionError(OrderError):
    """Order execution failed"""
    pass


class OrderValidationError(OrderError):
    """Order validation failed"""
    pass


class ConfigurationError(CopyTradingError):
    """Configuration error"""
    pass


class ValidationError(CopyTradingError):
    """Data validation error"""
    pass
