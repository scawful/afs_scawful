from __future__ import annotations

import random
from pathlib import Path

from afs_scawful.generators.asm_augment import AsmAugmentConfig, AsmAugmentGenerator
from afs_scawful.training import TrainingSample


def _make_generator(tmp_path: Path, count: int = 3) -> AsmAugmentGenerator:
    config = AsmAugmentConfig(
        input_path=tmp_path / "input.jsonl",
        output_path=tmp_path / "output.jsonl",
        paraphrase_count=count,
    )
    return AsmAugmentGenerator(config)


def test_clean_instruction_strips_markers(tmp_path: Path) -> None:
    generator = _make_generator(tmp_path)
    cleaned = generator._clean_instruction(
        "Implement the routine; *$EE1ED-$EE213 LOCAL. ==== -- TODO"
    )
    assert "$EE1ED" not in cleaned
    assert "====" not in cleaned
    assert "TODO" not in cleaned


def test_detect_category_ignores_org_word(tmp_path: Path) -> None:
    generator = _make_generator(tmp_path)
    assert generator._detect_category("Organize this routine for clarity.") == "write"
    assert generator._detect_category("org $EE1ED") == "hook"


def test_paraphrase_count_and_address_extraction(tmp_path: Path) -> None:
    random.seed(0)
    generator = _make_generator(tmp_path, count=5)
    sample = TrainingSample(
        instruction="Create an ASAR hook at $EE1ED to update the timer.",
        input="",
        output="LDA #$01\nSTA $0F30",
        domain="asm",
    )
    augmented = generator.generate_paraphrases(sample)

    assert len(augmented) == 5
    for item in augmented:
        assert "$EE1ED" in item.instruction
        assert item.metadata.get("address") == "$EE1ED"
