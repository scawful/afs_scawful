from __future__ import annotations

import asyncio

from afs_scawful.training import TrainingSample
from afs_scawful.validators import AsmValidator, CppValidator


def test_asm_validator_basic() -> None:
    sample = TrainingSample(
        instruction="",
        input="",
        output="LDA #$01\nSTA $7E0000\n",
        domain="asm",
        source="test",
    )
    result = asyncio.run(AsmValidator().validate(sample))
    assert result.valid
    assert result.score > 0.0


def test_cpp_validator_basic() -> None:
    sample = TrainingSample(
        instruction="",
        input="",
        output="int main() { return 0; }\n",
        domain="cpp",
        source="test",
    )
    result = asyncio.run(CppValidator(check_compile=False).validate(sample))
    assert result.valid
    assert result.score > 0.0
