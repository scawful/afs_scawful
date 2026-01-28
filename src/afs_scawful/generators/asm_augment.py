"""ASM Augmentation Generator for SNES 65816 assembly."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import BaseGenerator, GenerationResult
from ..training import TrainingSample
from ..integrations.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


@dataclass
class AsmAugmentConfig:
    """Configuration for ASM augmentation."""
    input_path: Path
    output_path: Path
    paraphrase_count: int = 3
    categories: list[str] = field(default_factory=lambda: ["write", "optimize", "debug", "hook"])
    use_llm: bool = False
    llm_model: str = "qwen2.5-coder:7b"
    ollama_url: str = "http://localhost:11434"
    generate_thinking: bool = False
    concurrency: int = 5


class AsmAugmentGenerator(BaseGenerator):
    """Generator for augmenting ASM training data via paraphrasing and CoT generation."""

    # Patterns to strip from instructions (ported from core afs)
    CLEANING_PATTERNS = [
        r";\s*\*?\$[0-9A-Fa-f]+-\$[0-9A-Fa-f]+\s*(LOCAL|LONG|JUMP|DATA|MAIN)?\.?",
        r"\*\$[0-9A-Fa-f]+-\$[0-9A-Fa-f]+\s*(LOCAL|LONG|JUMP|DATA|MAIN)?\.?",
        r"={4,}",
        r"-{4,}",
        r";\s*TODO\s*$",
        r";\s*\$[0-9A-Fa-f]+\s*$",
    ]

    TEMPLATES = {
        "write": {
            "technical": [
                "Implement a 65816 routine to {task}.",
                "Write a snippet in SNES assembly that {task}.",
                "Develop a 65816-compatible function for {task}.",
            ],
            "tutorial": [
                "How do I {task} using 65816 instructions?",
                "Show me an example of how to {task} in SNES ASM.",
                "Can you explain how to {task} and provide the 65816 code?",
            ],
            "concise": [
                "65816 routine: {task}.",
                "SNES code to {task}.",
                "{task} in 65816.",
            ]
        },
        "optimize": {
            "technical": [
                "Optimize this 65816 routine: {task}.",
                "Refactor the following SNES assembly snippet for performance: {task}.",
            ],
            "tutorial": [
                "How can I make this 65816 code that {task} more efficient?",
                "What's a faster way to {task} in 65816 assembly?",
            ],
            "concise": [
                "Optimize 65816: {task}.",
                "Refactor {task} for speed.",
            ]
        },
        "debug": {
            "technical": [
                "Identify the bug in this 65816 code: {task}.",
                "Debug the following SNES assembly routine: {task}.",
            ],
            "tutorial": [
                "Why is this 65816 logic failing to {task}?",
                "Explain the issue in this routine designed to {task}.",
            ],
            "concise": [
                "Fix 65816 bug: {task}.",
                "Debug {task}.",
            ]
        },
        "hook": {
            "technical": [
                "Create an ASAR hook at {address} to {task}.",
                "Write a patch at {address} that {task}.",
            ],
            "tutorial": [
                "How do I use an ASAR hook at {address} to {task}?",
                "Show me how to override the code at {address} to {task}.",
            ],
            "concise": [
                "Hook {address}: {task}.",
                "ASAR patch @ {address}: {task}.",
            ]
        }
    }

    def __init__(self, config: AsmAugmentConfig) -> None:
        super().__init__(name="asm_augment", domain="asm")
        self.config = config
        self.ollama = OllamaClient(base_url=config.ollama_url) if config.use_llm or config.generate_thinking else None
        self._cleaning_regexes = [re.compile(p, re.IGNORECASE) for p in self.CLEANING_PATTERNS]

    def _clean_instruction(self, instruction: str) -> str:
        """Clean technical markers and separators from instruction."""
        cleaned = instruction
        for regex in self._cleaning_regexes:
            cleaned = regex.sub("", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"(?:--\s*)?TODO\b.*$", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"[\s,;:]+$", "", cleaned).strip()
        return cleaned

    def _detect_category(self, instruction: str) -> str:
        """Detect the category of an instruction."""
        if re.search(r"\b(optimize|improve|refactor|efficient)\b", instruction, re.IGNORECASE):
            return "optimize"
        if re.search(r"\b(debug|fix|fail(?:ing)?|issue|error|bug)\b", instruction, re.IGNORECASE):
            return "debug"
        if re.search(r"\b(hook|asar|patch)\b", instruction, re.IGNORECASE) or re.search(
            r"\borg\s+\$[0-9A-Fa-f]{4,6}\b", instruction, re.IGNORECASE
        ):
            return "hook"
        return "write"

    def _extract_address(self, instruction: str) -> str | None:
        """Extract an address token (e.g., $02:8000, $1ABC, $EE1ED)."""
        patterns = [
            r"\$[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}",
            r"\$[0-9A-Fa-f]{6}",
            r"\$[0-9A-Fa-f]{5}",
            r"\$[0-9A-Fa-f]{4}",
        ]
        for pattern in patterns:
            match = re.search(pattern, instruction)
            if match:
                return match.group(0)
        return None

    def _extract_task(self, instruction: str, category: str, address: str | None = None) -> str:
        """Extract the core task from an instruction."""
        task = instruction.strip()
        patterns = [
            r"^(write|create|implement|provide|show|generate)\s+(a|an)?\s*(65816|snes|assembly|asm|asar|routine|snippet|code|logic)*\s*(to|that|for)?\s*",
            r"^(optimize|improve|refactor)\s+(this|the)?\s*(65816|snes|assembly|asm|asar|routine|snippet|code|logic)*\s*(that|to)?\s*",
            r"^(debug|fix|find the issue in|find the bug in)\s+(this|the)?\s*(65816|snes|assembly|asm|asar|routine|snippet|code|logic)*\s*(that|to)?\s*",
            r"^(create|write)\s+(a|an)?\s*(asar)?\s*hook\s+(at|to)\s*(\$[0-9A-Fa-f]{6})?\s*(to|that)?\s*",
        ]
        
        for pattern in patterns:
            match = re.match(pattern, task, re.IGNORECASE)
            if match:
                task = task[match.end():]
                break

        if address:
            task = task.replace(address, "").strip()
            task = re.sub(r"\b(at|to)\s*$", "", task, flags=re.IGNORECASE).strip()
        
        if task and task[0].islower():
            if not re.match(r"^[a-z]{3}\s", task):
                task = task[0].upper() + task[1:]
        
        return task.strip().rstrip(".?!")

    async def _generate_thinking(self, sample: TrainingSample) -> str | None:
        """Generate Chain of Thought for a sample using LLM."""
        if not self.ollama:
            return None
        
        system = (
            "You are an expert SNES 65816 assembly programmer. "
            "Explain the reasoning and logic behind the provided assembly code. "
            "Focus on register usage (A, X, Y), memory addresses, and 65816-specific modes (Native vs Emulation, 8-bit vs 16-bit)."
        )
        prompt = (
            f"Instruction: {sample.instruction}\n"
            f"Input context: {sample.input}\n\n"
            f"Assembly Code:\n{sample.output}\n\n"
            "Provide a concise step-by-step reasoning for this code."
        )
        
        try:
            resp = await self.ollama.generate(
                model=self.config.llm_model,
                prompt=prompt,
                system=system,
                max_tokens=512
            )
            if resp.error:
                logger.error("Thinking generation failed: %s", resp.error)
                return None
            return resp.text.strip()
        except Exception as e:
            logger.error(f"Failed to generate thinking: {e}")
            return None

    def generate_paraphrases(self, sample: TrainingSample) -> list[TrainingSample]:
        """Generate paraphrased versions using styled templates."""
        category = self._detect_category(sample.instruction)
        cleaned_instr = self._clean_instruction(sample.instruction)
        address = sample.metadata.get("address") or self._extract_address(cleaned_instr)
        task = self._extract_task(cleaned_instr, category, address=address)
        
        style_groups = self.TEMPLATES.get(category, self.TEMPLATES["write"])
        augmented = []
        seen_instructions = set()
        
        # Select one from each style to ensure variety
        for style, templates in style_groups.items():
            if len(augmented) >= self.config.paraphrase_count:
                break
                
            template = random.choice(templates)
            new_instruction = template.format(
                task=task, 
                address=address or "$XXXXXX"
            )
            
            if new_instruction.lower() in seen_instructions:
                continue
            seen_instructions.add(new_instruction.lower())

            metadata = {**sample.metadata, "original_instruction": sample.instruction}
            if address:
                metadata.setdefault("address", address)

            new_sample = TrainingSample(
                instruction=new_instruction,
                input=sample.input,
                output=sample.output,
                domain=sample.domain,
                thinking=sample.thinking,
                source=f"{self.name}_{style}",
                metadata=metadata,
            )
            augmented.append(new_sample)
            
        all_templates: list[tuple[str, str]] = []
        for style, templates in style_groups.items():
            for template in templates:
                all_templates.append((style, template))

        attempts = 0
        max_attempts = self.config.paraphrase_count * 5
        while len(augmented) < self.config.paraphrase_count and attempts < max_attempts:
            attempts += 1
            style, template = random.choice(all_templates)
            new_instruction = template.format(
                task=task,
                address=address or "$XXXXXX",
            )
            if new_instruction.lower() in seen_instructions:
                continue
            seen_instructions.add(new_instruction.lower())

            metadata = {**sample.metadata, "original_instruction": sample.instruction}
            if address:
                metadata.setdefault("address", address)

            augmented.append(
                TrainingSample(
                    instruction=new_instruction,
                    input=sample.input,
                    output=sample.output,
                    domain=sample.domain,
                    thinking=sample.thinking,
                    source=f"{self.name}_{style}",
                    metadata=metadata,
                )
            )

        return augmented

    async def augment_batch(self, samples: list[TrainingSample]) -> list[TrainingSample]:
        """Perform augmentation and thinking generation on a batch."""
        all_augmented = []
        
        # 1. Paraphrasing
        for sample in samples:
            # Generate thinking for original if needed
            all_augmented.append(sample)
            all_augmented.extend(self.generate_paraphrases(sample))
            
        # 2. Thinking Generation (if enabled)
        if self.config.generate_thinking:
            semaphore = asyncio.Semaphore(self.config.concurrency)
            
            async def process_thinking(s: TrainingSample):
                async with semaphore:
                    if not s.thinking:
                        thought = await self._generate_thinking(s)
                        if thought:
                            s.thinking = thought
            
            # Use gather to process all samples concurrently
            tasks = [process_thinking(s) for s in all_augmented]
            await asyncio.gather(*tasks)
            
        return all_augmented

    def generate(self) -> GenerationResult:
        """Generate augmented samples (sync wrapper)."""
        return asyncio.run(self.generate_async())

    async def generate_async(self) -> GenerationResult:
        """Generate augmented samples asynchronously."""
        import json
        
        result = GenerationResult()
        if not self.config.input_path.exists():
            result.errors.append(f"Input path does not exist: {self.config.input_path}")
            return result

        samples = []
        try:
            with open(self.config.input_path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    samples.append(TrainingSample.from_dict(json.loads(line)))
        except Exception as e:
            result.errors.append(f"Failed to read input file: {e}")
            return result

        result.samples = await self.augment_batch(samples)
        return result
