"""Validator registry for AFS Scawful."""

from .asar_validator import AsarValidator
from .asm_validator import AsmValidator
from .base import CompositeValidator, ValidationResult, Validator
from .cpp_validator import CppValidator
from .kg_validator import KGValidator

__all__ = [
    "AsarValidator",
    "AsmValidator",
    "CppValidator",
    "CompositeValidator",
    "KGValidator",
    "ValidationResult",
    "Validator",
    "default_validators",
]


def default_validators() -> list[Validator]:
    return [
        AsmValidator(),
        AsarValidator(),
        CppValidator(),
        KGValidator(),
    ]
