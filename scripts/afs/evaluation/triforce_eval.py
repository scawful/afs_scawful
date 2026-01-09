#!/usr/bin/env python3
"""Triforce Expert Model Evaluation Suite.

Tests each expert model on domain-specific tasks and documents gaps.
"""

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from afs.agent import AgentHarness, HarnessConfig, TRIFORCE_TOOLS, ModelConfig

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """Single test case for expert evaluation."""
    name: str
    prompt: str
    expected_keywords: list[str]  # Keywords that should appear in response
    expected_ops: list[str] = field(default_factory=list)  # Assembly ops expected
    anti_keywords: list[str] = field(default_factory=list)  # Keywords indicating wrong answer
    category: str = "general"


@dataclass
class TestResult:
    """Result from running a test case."""
    test_name: str
    expert: str
    passed: bool
    score: float  # 0-1 based on keyword matches
    response: str
    latency_ms: float
    error: str | None = None
    missing_keywords: list[str] = field(default_factory=list)
    found_anti_keywords: list[str] = field(default_factory=list)


# ============================================================================
# Test Suites for Each Expert
# ============================================================================

NAYRU_TESTS = [
    # Code generation tests
    TestCase(
        name="dma_transfer_basic",
        prompt="Write 65816 assembly code to perform a DMA transfer of 32 bytes from ROM address $008000 to VRAM address $2000. Include all necessary register setup.",
        expected_keywords=["REP", "LDA", "STA", "$4300", "$4301", "$4302", "$420B"],
        expected_ops=["REP", "LDA", "STA"],
        category="code_generation",
    ),
    TestCase(
        name="controller_read",
        prompt="Write 65816 assembly to read controller 1 input and check if the A button is pressed, branching to a label called 'AButtonPressed' if so.",
        expected_keywords=["$4218", "AND", "BNE", "LDA"],
        expected_ops=["LDA", "AND", "BNE"],
        category="code_generation",
    ),
    TestCase(
        name="wait_vblank",
        prompt="Write assembly code to wait for vertical blank on the SNES using the NMI flag.",
        expected_keywords=["$4210", "BPL", "LDA", "loop"],
        expected_ops=["LDA", "BPL"],
        category="code_generation",
    ),
    TestCase(
        name="sprite_upload",
        prompt="Write 65816 code to upload 512 bytes of sprite data to OAM using DMA.",
        expected_keywords=["$4300", "$2104", "OAM", "DMA", "$420B"],
        expected_ops=["LDA", "STA"],
        category="code_generation",
    ),
    TestCase(
        name="16bit_multiply",
        prompt="Write 65816 assembly to multiply two 16-bit values in registers A and X, storing the 32-bit result.",
        expected_keywords=["REP", "LDA", "STA", "MUL"],
        expected_ops=["REP", "LDA"],
        anti_keywords=["sorry", "cannot", "don't know"],
        category="code_generation",
    ),
]

DIN_TESTS = [
    # Optimization tests
    TestCase(
        name="optimize_zero_store",
        prompt="Optimize this 65816 code:\nLDA #$00\nSTA $10\n\nWhat is the optimal replacement?",
        expected_keywords=["STZ", "$10"],
        expected_ops=["STZ"],
        anti_keywords=["LDA #$00"],
        category="optimization",
    ),
    TestCase(
        name="optimize_increment",
        prompt="Optimize this sequence:\nLDA $10\nCLC\nADC #$01\nSTA $10\n\nHow can this be reduced?",
        expected_keywords=["INC"],
        expected_ops=["INC"],
        anti_keywords=["CLC", "ADC"],
        category="optimization",
    ),
    TestCase(
        name="optimize_branch",
        prompt="What's wrong with this code and how to optimize it?\nCMP #$00\nBEQ skip\n\nThe comparison is redundant because...",
        expected_keywords=["BEQ", "zero", "flag"],
        anti_keywords=["correct", "nothing wrong"],
        category="optimization",
    ),
    TestCase(
        name="optimize_mode_switch",
        prompt="This code switches modes inefficiently:\nSEP #$20\nLDA $10\nREP #$20\nSEP #$20\nLDA $11\n\nHow to optimize?",
        expected_keywords=["SEP", "mode", "remove", "unnecessary"],
        anti_keywords=["looks fine", "nothing"],
        category="optimization",
    ),
    TestCase(
        name="optimize_loop",
        prompt="Optimize this loop for speed:\nLDX #$00\nloop:\nLDA table,X\nSTA $2100\nINX\nCPX #$10\nBNE loop",
        expected_keywords=["DEX", "BNE", "faster", "backward"],
        category="optimization",
    ),
]

FARORE_TESTS = [
    # Bug detection tests
    TestCase(
        name="detect_mode_mismatch",
        prompt="Find the bug in this code:\nREP #$20\nLDA.w $10\nSTA.b $12\n\nWhat's wrong?",
        expected_keywords=["mode", "16-bit", "8-bit", "mismatch", "size"],
        category="debugging",
    ),
    TestCase(
        name="detect_missing_sep",
        prompt="What bug exists here?\nREP #$20\nLDA #$1234\nSTA $10\nLDA #$56\nSTA $12\n; expected $12 to be $56 but it's $1256",
        expected_keywords=["SEP", "8-bit", "16-bit", "mode"],
        category="debugging",
    ),
    TestCase(
        name="detect_stack_corruption",
        prompt="Debug this:\nPHA\nJSR subroutine\nPLA\n; crashes on PLA\n\nsubroutine:\nPHA\nRTS",
        expected_keywords=["stack", "PHA", "PLA", "imbalance", "unmatched"],
        category="debugging",
    ),
    TestCase(
        name="detect_register_clobber",
        prompt="Find why Y is wrong after this:\nLDY #$05\nJSR ProcessData\n; expected Y=5 but it's 0\n\nProcessData:\nLDY #$00\n...\nRTS",
        expected_keywords=["Y", "clobber", "preserve", "PHY", "PLY"],
        category="debugging",
    ),
    TestCase(
        name="detect_dma_error",
        prompt="DMA isn't transferring. Find the bug:\nLDA #$01\nSTA $4300\nLDA #$80\nSTA $4301\nLDA #$00\nSTA $4302\nLDA #$80\nSTA $4303\nLDA #$00\nSTA $4304\nLDA #$01\nSTA $420B",
        expected_keywords=["$4305", "$4306", "length", "size", "count"],
        category="debugging",
    ),
]

VERAN_TESTS = [
    # Hardware knowledge tests
    TestCase(
        name="identify_inidisp",
        prompt="What is the SNES register $2100 used for?",
        expected_keywords=["INIDISP", "screen", "brightness", "display", "blanking"],
        category="hardware_knowledge",
    ),
    TestCase(
        name="identify_dma_channel",
        prompt="Explain what registers $4300-$4305 control on the SNES.",
        expected_keywords=["DMA", "channel", "source", "destination", "transfer"],
        category="hardware_knowledge",
    ),
    TestCase(
        name="explain_mode7",
        prompt="What is Mode 7 on the SNES and what registers control it?",
        expected_keywords=["rotation", "scaling", "matrix", "$211B", "$211C"],
        anti_keywords=["don't know", "not sure"],
        category="hardware_knowledge",
    ),
    TestCase(
        name="explain_hdma",
        prompt="How does HDMA differ from regular DMA on the SNES?",
        expected_keywords=["scanline", "horizontal", "table", "$420C"],
        category="hardware_knowledge",
    ),
    TestCase(
        name="ram_map_link",
        prompt="In A Link to the Past, what RAM address stores Link's X coordinate on the overworld?",
        expected_keywords=["$7E", "$22", "position", "coordinate"],
        anti_keywords=["don't know", "not sure", "cannot"],
        category="alttp_knowledge",
    ),
]

# New expert test suites
ONOX_TESTS = [
    # Data architecture tests
    TestCase(
        name="jump_table_16bit",
        prompt="Create a 65816 jump table for 4 state handlers (Idle, Walk, Attack, Die) with 16-bit pointers.",
        expected_keywords=["dw", "JMP", "ASL", "TAX"],
        expected_ops=["dw", "JMP"],
        category="data_architecture",
    ),
    TestCase(
        name="sprite_table_format",
        prompt="Design a sprite definition table entry format for SNES with: AI type, HP, damage, graphics set, palette, and flags.",
        expected_keywords=["db", "sprite", "HP", "flags"],
        category="data_architecture",
    ),
    TestCase(
        name="bitfield_design",
        prompt="Design a compact bitfield byte for sprite state: active (1 bit), direction (2 bits), state (3 bits), frame (2 bits). Show the masks.",
        expected_keywords=["bit", "mask", "%", "AND"],
        category="data_architecture",
    ),
    TestCase(
        name="palette_table",
        prompt="Create a 4-color SNES palette table in 15-bit BGR format for: black, white, red, blue.",
        expected_keywords=["dw", "$0000", "$7FFF", "BGR"],
        category="data_architecture",
    ),
    TestCase(
        name="bank_alignment",
        prompt="What are the considerations for placing large data tables across SNES ROM banks?",
        expected_keywords=["bank", "address", "32KB", "boundary"],
        category="data_architecture",
    ),
]

TWINROVA_TESTS = [
    # State machine and memory tests
    TestCase(
        name="state_machine_basic",
        prompt="Write a 65816 state machine dispatcher that uses A register as state index to jump to handlers.",
        expected_keywords=["ASL", "TAX", "JMP", "RTS"],
        expected_ops=["ASL", "TAX", "JMP"],
        category="state_machine",
    ),
    TestCase(
        name="bitfield_flag_set",
        prompt="Write 65816 code to set bit 3 of a progress flags byte at $7EF3D6.",
        expected_keywords=["ORA", "#%", "STA", "$7EF3D6"],
        expected_ops=["LDA", "ORA", "STA"],
        category="memory_management",
    ),
    TestCase(
        name="bitfield_flag_check",
        prompt="Write 65816 code to check if bit 5 is set in a flags byte at $7EF3D6, branching if not set.",
        expected_keywords=["AND", "#%", "BEQ", "$7EF3D6"],
        expected_ops=["LDA", "AND", "BEQ"],
        category="memory_management",
    ),
    TestCase(
        name="substate_pattern",
        prompt="Explain the substate pattern for complex behaviors where main state has multiple phases.",
        expected_keywords=["substate", "INC", "transition", "phase"],
        category="state_machine",
    ),
    TestCase(
        name="wram_allocation",
        prompt="How should you allocate new WRAM variables for an ALTTP ROM hack in the Oracle of Secrets custom region?",
        expected_keywords=["$7E0730", "document", "16-bit", "align"],
        category="memory_management",
    ),
]

AGAHNIM_TESTS = [
    # Build and integration tests
    TestCase(
        name="hook_pattern",
        prompt="Write an asar hook that replaces code at $008000 with a JSL to your new routine.",
        expected_keywords=["pushpc", "pullpc", "org", "JSL"],
        category="build_integration",
    ),
    TestCase(
        name="namespace_bridge",
        prompt="Explain how to call a function in the Oracle namespace from ZScream code that has no namespace.",
        expected_keywords=["namespace", "Oracle_", "bridge", "export"],
        category="build_integration",
    ),
    TestCase(
        name="org_directive",
        prompt="What is the purpose of the org directive in asar assembler?",
        expected_keywords=["org", "address", "ROM", "place"],
        category="build_integration",
    ),
    TestCase(
        name="assert_boundary",
        prompt="How do you protect against bank overflow in asar assembly?",
        expected_keywords=["assert", "pc()", "overflow", "bank"],
        category="build_integration",
    ),
    TestCase(
        name="incsrc_order",
        prompt="Why does the order of incsrc directives matter in asar?",
        expected_keywords=["order", "label", "defined", "before"],
        category="build_integration",
    ),
]


# ============================================================================
# Evaluation Engine
# ============================================================================

class TriforceEvaluator:
    """Evaluates Triforce expert models."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: list[TestResult] = []

    async def run_test(
        self,
        expert: str,
        model_id: str,
        test: TestCase,
    ) -> TestResult:
        """Run a single test case."""
        start_time = time.time()

        config = HarnessConfig(max_iterations=3, verbose=self.verbose)
        harness = AgentHarness(model_id, tools=None, config=config)  # Explicitly None to skip tools
        harness.tools = {}  # Clear default AFS_TOOLS for models without tool support

        try:
            async with harness:
                result = await harness.run(test.prompt)
                response = result.response.lower()
                latency = (time.time() - start_time) * 1000

                # Check expected keywords
                found_keywords = []
                missing_keywords = []
                for kw in test.expected_keywords:
                    if kw.lower() in response:
                        found_keywords.append(kw)
                    else:
                        missing_keywords.append(kw)

                # Check anti-keywords
                found_anti = [kw for kw in test.anti_keywords if kw.lower() in response]

                # Calculate score
                if test.expected_keywords:
                    score = len(found_keywords) / len(test.expected_keywords)
                else:
                    score = 1.0 if not found_anti else 0.0

                # Penalize for anti-keywords
                if found_anti:
                    score *= 0.5

                passed = score >= 0.6 and not found_anti

                return TestResult(
                    test_name=test.name,
                    expert=expert,
                    passed=passed,
                    score=score,
                    response=result.response[:500],  # Truncate for report
                    latency_ms=latency,
                    missing_keywords=missing_keywords,
                    found_anti_keywords=found_anti,
                )

        except Exception as e:
            return TestResult(
                test_name=test.name,
                expert=expert,
                passed=False,
                score=0.0,
                response="",
                latency_ms=(time.time() - start_time) * 1000,
                error=str(e),
            )

    async def evaluate_expert(
        self,
        expert: str,
        model_id: str,
        tests: list[TestCase],
    ) -> list[TestResult]:
        """Evaluate an expert on a test suite."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Evaluating {expert} ({model_id})")
        logger.info(f"{'='*60}")

        results = []
        for i, test in enumerate(tests):
            logger.info(f"  [{i+1}/{len(tests)}] {test.name}...")
            result = await self.run_test(expert, model_id, test)
            results.append(result)
            self.results.append(result)

            status = "✓" if result.passed else "✗"
            logger.info(f"    {status} Score: {result.score:.2f} ({result.latency_ms:.0f}ms)")
            if result.missing_keywords:
                logger.info(f"    Missing: {result.missing_keywords}")
            if result.error:
                logger.info(f"    Error: {result.error}")

        # Summary for this expert
        passed = sum(1 for r in results if r.passed)
        avg_score = sum(r.score for r in results) / len(results) if results else 0
        logger.info(f"\n  Summary: {passed}/{len(tests)} passed, avg score: {avg_score:.2f}")

        return results

    async def run_full_evaluation(self) -> dict[str, Any]:
        """Run evaluation on all experts."""
        experts = {
            "nayru": ("nayru-v7:latest", NAYRU_TESTS),
            "din": ("din-v4:latest", DIN_TESTS),
            "farore": ("farore-v4:latest", FARORE_TESTS),
            "veran": ("veran-v2:latest", VERAN_TESTS),
            "onox": ("onox-v1:latest", ONOX_TESTS),
            "twinrova": ("twinrova-v1:latest", TWINROVA_TESTS),
            "agahnim": ("agahnim-v1:latest", AGAHNIM_TESTS),
        }

        all_results = {}
        for expert, (model_id, tests) in experts.items():
            results = await self.evaluate_expert(expert, model_id, tests)
            all_results[expert] = {
                "model_id": model_id,
                "tests": len(tests),
                "passed": sum(1 for r in results if r.passed),
                "avg_score": sum(r.score for r in results) / len(results) if results else 0,
                "avg_latency_ms": sum(r.latency_ms for r in results) / len(results) if results else 0,
                "details": [
                    {
                        "name": r.test_name,
                        "passed": r.passed,
                        "score": r.score,
                        "missing": r.missing_keywords,
                        "response_preview": r.response[:200],
                    }
                    for r in results
                ],
            }

        return all_results

    def generate_gap_report(self) -> str:
        """Generate a knowledge gap report from results."""
        report = []
        report.append("# Triforce Expert Knowledge Gap Analysis")
        report.append(f"\n*Generated: {datetime.now().isoformat()}*\n")

        # Group by expert
        by_expert: dict[str, list[TestResult]] = {}
        for r in self.results:
            by_expert.setdefault(r.expert, []).append(r)

        for expert, results in by_expert.items():
            passed = sum(1 for r in results if r.passed)
            total = len(results)
            avg = sum(r.score for r in results) / total if total else 0

            report.append(f"\n## {expert.title()}")
            report.append(f"\n**Overall:** {passed}/{total} tests passed ({avg*100:.1f}%)\n")

            # Failed tests
            failed = [r for r in results if not r.passed]
            if failed:
                report.append("### Knowledge Gaps\n")
                for r in failed:
                    report.append(f"#### {r.test_name}")
                    report.append(f"- **Score:** {r.score:.2f}")
                    if r.missing_keywords:
                        report.append(f"- **Missing concepts:** {', '.join(r.missing_keywords)}")
                    if r.found_anti_keywords:
                        report.append(f"- **Concerning phrases:** {', '.join(r.found_anti_keywords)}")
                    if r.error:
                        report.append(f"- **Error:** {r.error}")
                    report.append(f"- **Response preview:** `{r.response[:150]}...`\n")

            # Identify patterns
            missing_all = []
            for r in results:
                missing_all.extend(r.missing_keywords)

            if missing_all:
                from collections import Counter
                common = Counter(missing_all).most_common(5)
                report.append("### Most Commonly Missing Concepts\n")
                for concept, count in common:
                    report.append(f"- `{concept}` (missing {count}x)")

        return "\n".join(report)


async def main():
    """Run evaluation."""
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate Triforce expert models")
    parser.add_argument("--expert", choices=["nayru", "din", "farore", "veran", "onox", "twinrova", "agahnim", "all"], default="all")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--output", "-o", default="triforce_eval_results.json")
    args = parser.parse_args()

    evaluator = TriforceEvaluator(verbose=args.verbose)

    if args.expert == "all":
        results = await evaluator.run_full_evaluation()
    else:
        experts = {
            "nayru": ("nayru-v7:latest", NAYRU_TESTS),
            "din": ("din-v4:latest", DIN_TESTS),
            "farore": ("farore-v4:latest", FARORE_TESTS),
            "veran": ("veran-v2:latest", VERAN_TESTS),
            "onox": ("onox-v1:latest", ONOX_TESTS),
            "twinrova": ("twinrova-v1:latest", TWINROVA_TESTS),
            "agahnim": ("agahnim-v1:latest", AGAHNIM_TESTS),
        }
        model_id, tests = experts[args.expert]
        eval_results = await evaluator.evaluate_expert(args.expert, model_id, tests)
        results = {
            args.expert: {
                "model_id": model_id,
                "tests": len(tests),
                "passed": sum(1 for r in eval_results if r.passed),
                "avg_score": sum(r.score for r in eval_results) / len(eval_results),
                "details": [
                    {"name": r.test_name, "passed": r.passed, "score": r.score}
                    for r in eval_results
                ],
            }
        }

    # Save results
    output_path = Path(args.output)
    output_path.write_text(json.dumps(results, indent=2))
    logger.info(f"\nResults saved to {output_path}")

    # Generate gap report
    gap_report = evaluator.generate_gap_report()
    gap_path = Path("triforce_gaps.md")
    gap_path.write_text(gap_report)
    logger.info(f"Gap report saved to {gap_path}")

    # Print summary
    print("\n" + "="*60)
    print("EVALUATION SUMMARY")
    print("="*60)
    for expert, data in results.items():
        print(f"\n{expert.upper()}: {data['passed']}/{data['tests']} ({data['avg_score']*100:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
