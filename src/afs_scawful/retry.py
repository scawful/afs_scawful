"""Retry utilities with exponential backoff.

Provides decorators and utilities for retrying operations that may fail transiently.
"""

from __future__ import annotations

import functools
import random
import time
from dataclasses import dataclass
from typing import Callable, Optional, Type, TypeVar, Any

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 5
    base_delay: float = 1.0
    max_delay: float = 300.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,)


def calculate_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    exponential_base: float,
    jitter: bool,
) -> float:
    """Calculate delay for a given attempt using exponential backoff.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap
        exponential_base: Base for exponential calculation
        jitter: If True, add random jitter

    Returns:
        Delay in seconds
    """
    delay = base_delay * (exponential_base**attempt)
    delay = min(delay, max_delay)

    if jitter:
        # Add up to 25% random jitter
        jitter_amount = delay * 0.25 * random.random()
        delay = delay + jitter_amount

    return delay


def retry_with_backoff(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 300.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for retrying functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay cap (seconds)
        exponential_base: Base for exponential calculation
        jitter: If True, add random jitter to delays
        retryable_exceptions: Tuple of exception types to retry on
        on_retry: Optional callback called on each retry (exception, attempt)

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        # Final attempt failed
                        raise

                    if on_retry:
                        on_retry(e, attempt)

                    delay = calculate_delay(
                        attempt, base_delay, max_delay, exponential_base, jitter
                    )
                    time.sleep(delay)

            # Should never reach here, but satisfy type checker
            assert last_exception is not None
            raise last_exception

        return wrapper

    return decorator


class RetryableOperation:
    """Context manager for retryable operations with explicit control."""

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self.attempt = 0
        self.last_exception: Optional[Exception] = None

    def should_retry(self, exception: Exception) -> bool:
        """Check if we should retry after an exception."""
        if self.attempt >= self.config.max_retries:
            return False

        if not isinstance(exception, self.config.retryable_exceptions):
            return False

        return True

    def wait_before_retry(self) -> None:
        """Wait the appropriate delay before the next retry."""
        delay = calculate_delay(
            self.attempt,
            self.config.base_delay,
            self.config.max_delay,
            self.config.exponential_base,
            self.config.jitter,
        )
        time.sleep(delay)
        self.attempt += 1

    def run(self, operation: Callable[[], T]) -> T:
        """Run an operation with retries.

        Args:
            operation: Callable to execute

        Returns:
            Result of the operation

        Raises:
            The last exception if all retries fail
        """
        while True:
            try:
                return operation()
            except self.config.retryable_exceptions as e:
                self.last_exception = e
                if not self.should_retry(e):
                    raise
                self.wait_before_retry()


# Network-specific retry configurations
NETWORK_RETRY_CONFIG = RetryConfig(
    max_retries=5,
    base_delay=2.0,
    max_delay=120.0,
    exponential_base=2.0,
    jitter=True,
    retryable_exceptions=(
        ConnectionError,
        TimeoutError,
        OSError,
    ),
)

# Quick retry for transient failures
QUICK_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=0.5,
    max_delay=10.0,
    exponential_base=2.0,
    jitter=True,
)


def network_retry(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator for network operations with sensible defaults."""
    return retry_with_backoff(
        max_retries=NETWORK_RETRY_CONFIG.max_retries,
        base_delay=NETWORK_RETRY_CONFIG.base_delay,
        max_delay=NETWORK_RETRY_CONFIG.max_delay,
        retryable_exceptions=NETWORK_RETRY_CONFIG.retryable_exceptions,
    )(func)


# Shell script integration
if __name__ == "__main__":
    import subprocess
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m afs_scawful.retry <command> [args...]")
        print("Retries the command with exponential backoff on failure.")
        sys.exit(1)

    command = sys.argv[1:]

    def run_command() -> int:
        result = subprocess.run(command, capture_output=False)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, command)
        return result.returncode

    retry_op = RetryableOperation(NETWORK_RETRY_CONFIG)

    try:
        exit_code = retry_op.run(run_command)
        sys.exit(exit_code)
    except subprocess.CalledProcessError as e:
        print(f"Command failed after {retry_op.attempt + 1} attempts: {e}")
        sys.exit(e.returncode)
