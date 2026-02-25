#!/usr/bin/env python3
"""
Cloud model distillation pipeline.

Queries cloud models (Anthropic, OpenAI, Google) with assembly prompts,
ASAR-validates all code responses, and filters to passing samples for
local model fine-tuning.

Usage:
    python scripts/distill_cloud.py \
        --prompts docs/eval/asar_eval_v1.jsonl \
        --models opus-4.6,sonnet-4.6,codex-5.3,gemini-3.1-pro \
        --output distill_cloud_v1.jsonl \
        --min-score 0.6
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from afs_scawful.chat_harness import build_provider, load_chat_registry
from afs_scawful.validators.asar_validator_v2 import AsarValidatorV2
from afs_scawful.training import TrainingSample

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert 65816 assembly programmer for the Super Nintendo. "
    "Output only valid 65816 assembly code. Use asar-compatible syntax. "
    "Include comments explaining the logic."
)


@dataclass(frozen=True)
class ResolvedModel:
    name: str
    provider: str
    model_id: str
    options: dict[str, object]


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    aliases = {
        "gemini": "studio",
        "google": "studio",
        "google-studio": "studio",
    }
    return aliases.get(normalized, normalized)


def _resolve_models(model_names: list[str], registry_path: Path | None) -> list[ResolvedModel]:
    """Resolve model aliases from chat_registry.toml."""
    registry = load_chat_registry(registry_path)
    resolved: list[ResolvedModel] = []

    for name in model_names:
        if name in registry.models:
            model = registry.models[name]
            resolved.append(
                ResolvedModel(
                    name=name,
                    provider=_normalize_provider(model.provider),
                    model_id=model.model_id,
                    options=model.options,
                )
            )
            continue

        # Fallback format: provider:model_id
        if ":" in name:
            provider, model_id = name.split(":", 1)
            provider = _normalize_provider(provider)
            model_id = model_id.strip()
            if provider in {"anthropic", "openai", "studio", "vertex"} and model_id:
                resolved.append(
                    ResolvedModel(
                        name=name,
                        provider=provider,
                        model_id=model_id,
                        options={},
                    )
                )
                continue

        raise ValueError(
            f"Model '{name}' not found in chat registry. "
            "Add it to config/chat_registry.toml or pass provider:model_id."
        )

    return resolved


def _build_clients(models: list[ResolvedModel]) -> dict[str, object]:
    """Build one provider client per resolved provider."""
    providers = {model.provider for model in models}
    return {provider: build_provider(provider) for provider in providers}


async def query_model(
    clients: dict[str, object],
    resolved_model: ResolvedModel,
    prompt_text: str,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> tuple[str, str | None]:
    """Query a cloud model and return (response_text, error)."""
    provider = resolved_model.provider
    model_id = resolved_model.model_id
    client = clients.get(provider)
    if client is None:
        return "", f"No client for provider: {provider}"

    try:
        messages = [{"role": "user", "content": prompt_text}]
        response = await client.chat(
            model=model_id,
            messages=messages,
            system=SYSTEM_PROMPT,
            temperature=temperature,
            max_tokens=max_tokens,
            options=resolved_model.options,
        )
        if response.error:
            return "", response.error
        return response.text, None
    except Exception as e:
        return "", str(e)


async def validate_response(
    validator: AsarValidatorV2,
    instruction: str,
    output_text: str,
) -> tuple[bool, float]:
    """Validate a code response with ASAR v2."""
    sample = TrainingSample(
        instruction=instruction,
        output=output_text,
        input="",
        domain="asm",
        source="distillation",
    )
    try:
        result = await validator.validate(sample)
        return result.valid, result.score
    except Exception:
        return False, 0.0


async def distill(
    prompts_path: Path,
    model_names: list[str],
    output_path: Path,
    registry_path: Path | None = None,
    min_score: float = 0.6,
    concurrency: int = 3,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> dict:
    """Run distillation pipeline."""
    resolved_models = _resolve_models(model_names, registry_path)
    clients = _build_clients(resolved_models)
    validator = AsarValidatorV2(semantic_analysis=True)

    # Load prompts
    prompts = []
    with open(prompts_path) as f:
        for line in f:
            line = line.strip()
            if line:
                prompts.append(json.loads(line))

    logger.info(f"Loaded {len(prompts)} prompts from {prompts_path}")
    logger.info(
        "Models: %s",
        [
            f"{model.name} ({model.provider}:{model.model_id})"
            for model in resolved_models
        ],
    )
    logger.info(f"Min score: {min_score}")

    results = []
    stats = {
        "total_queries": 0,
        "total_errors": 0,
        "total_passed": 0,
        "total_failed": 0,
        "by_model": {},
    }

    semaphore = asyncio.Semaphore(concurrency)

    async def process_one(prompt_data: dict, resolved_model: ResolvedModel):
        async with semaphore:
            instruction = prompt_data["instruction"]
            category = prompt_data.get("category", "")
            model_name = resolved_model.name

            stats["total_queries"] += 1

            response_text, error = await query_model(
                clients,
                resolved_model,
                instruction,
                temperature=temperature, max_tokens=max_tokens,
            )

            model_stats = stats["by_model"].setdefault(model_name, {
                "queries": 0, "errors": 0, "passed": 0, "failed": 0,
            })
            model_stats["queries"] += 1

            if error:
                stats["total_errors"] += 1
                model_stats["errors"] += 1
                logger.warning(f"[{model_name}] Error: {error[:80]}")
                return

            # Validate
            valid, score = await validate_response(
                validator, instruction, response_text,
            )

            if valid and score >= min_score:
                stats["total_passed"] += 1
                model_stats["passed"] += 1

                sample = {
                    "instruction": instruction,
                    "output": response_text,
                    "input": "",
                    "thinking": None,
                    "domain": "asm",
                    "source": "distillation",
                    "sample_id": str(uuid.uuid4()),
                    "quality_score": score,
                    "embedding": None,
                    "teacher_model": model_name,
                    "teacher_prompt": SYSTEM_PROMPT,
                    "timestamp": datetime.now().isoformat(),
                    "kg_entities": [],
                    "kg_validated": False,
                    "_metadata": {
                        "distillation_model": model_name,
                        "distillation_score": score,
                        "category": category,
                        "asar_validated": True,
                    },
                }
                results.append(sample)
                logger.info(
                    f"[{model_name}] PASS score={score:.2f} "
                    f"cat={category}"
                )
            else:
                stats["total_failed"] += 1
                model_stats["failed"] += 1
                logger.info(
                    f"[{model_name}] FAIL score={score:.2f} "
                    f"valid={valid} cat={category}"
                )

    # Build all tasks
    tasks = []
    for prompt_data in prompts:
        for resolved_model in resolved_models:
            tasks.append(process_one(prompt_data, resolved_model))

    logger.info(f"Running {len(tasks)} queries...")
    start_time = time.time()
    await asyncio.gather(*tasks)
    elapsed = time.time() - start_time

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for sample in results:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    # Summary
    stats["elapsed_seconds"] = elapsed
    stats["output_samples"] = len(results)

    print(f"\n{'='*60}")
    print(f"Distillation Complete")
    print(f"{'='*60}")
    print(f"Total queries: {stats['total_queries']}")
    print(f"Errors: {stats['total_errors']}")
    print(f"Passed (score >= {min_score}): {stats['total_passed']}")
    print(f"Failed: {stats['total_failed']}")
    print(f"Output samples: {len(results)}")
    print(f"Duration: {elapsed:.1f}s")
    print(f"Output: {output_path}")

    print(f"\nPer-model breakdown:")
    for model, ms in sorted(stats["by_model"].items()):
        rate = ms["passed"] / ms["queries"] * 100 if ms["queries"] > 0 else 0
        print(
            f"  {model:<25} queries={ms['queries']} "
            f"pass={ms['passed']} fail={ms['failed']} "
            f"err={ms['errors']} rate={rate:.0f}%"
        )

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Distill cloud model outputs for local fine-tuning."
    )
    parser.add_argument(
        "--prompts", "-p", required=True,
        help="JSONL file with prompts (instruction + category fields).",
    )
    parser.add_argument(
        "--models", "-m", required=True,
        help="Comma-separated model names (e.g., opus-4.6,sonnet-4.6).",
    )
    parser.add_argument(
        "--output", "-o", required=True,
        help="Output JSONL path for passing samples.",
    )
    parser.add_argument(
        "--registry",
        help=(
            "Optional chat registry TOML path. "
            "Defaults to config/chat_registry.toml."
        ),
    )
    parser.add_argument(
        "--min-score", type=float, default=0.6,
        help="Minimum validation score to keep (default: 0.6).",
    )
    parser.add_argument(
        "--concurrency", "-c", type=int, default=3,
        help="Max concurrent queries (default: 3).",
    )
    parser.add_argument(
        "--temperature", "-t", type=float, default=0.3,
        help="Sampling temperature (default: 0.3).",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=1024,
        help="Max output tokens (default: 1024).",
    )
    args = parser.parse_args()

    model_names = [m.strip() for m in args.models.split(",")]
    prompts_path = Path(args.prompts).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    registry_path = (
        Path(args.registry).expanduser().resolve() if args.registry else None
    )

    asyncio.run(distill(
        prompts_path=prompts_path,
        model_names=model_names,
        output_path=output_path,
        registry_path=registry_path,
        min_score=args.min_score,
        concurrency=args.concurrency,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    ))


if __name__ == "__main__":
    main()
