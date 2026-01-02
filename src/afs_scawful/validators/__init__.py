"""Validator registry for AFS Scawful."""

from .asar_validator import AsarValidator
from .asar_validator_v2 import AsarValidatorV2
from .asm_validator import AsmValidator
from .base import CompositeValidator, ValidationResult, Validator
from .cpp_validator import CppValidator
from .kg_validator import KGValidator

__all__ = [
    "AsarValidator",
    "AsarValidatorV2",
    "AsmValidator",
    "CppValidator",
    "CompositeValidator",
    "KGValidator",
    "ValidationResult",
    "Validator",
    "default_validators",
    "enhanced_validators",
]


def default_validators() -> list[Validator]:
    """Return default validators for backward compatibility."""
    return [
        AsmValidator(),
        AsarValidator(),
        CppValidator(),
        KGValidator(),
    ]


def enhanced_validators() -> list[Validator]:
    """Return enhanced validators with AsarValidatorV2."""
    return [
        AsmValidator(),
        AsarValidatorV2(),
        CppValidator(),
        KGValidator(),
    ]
