"""Configuration for eval pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


@dataclass
class PromptConfig:
    """Configuration for prompt generation."""
    categories: list[str] = field(default_factory=lambda: [
        "code_generation",
        "code_explanation",
        "bug_fixing",
        "optimization",
        "documentation",
    ])
    templates_path: Path | None = None
    custom_prompts: list[dict[str, str]] = field(default_factory=list)
    max_prompts_per_category: int = 10


@dataclass
class ValidationConfig:
    """Configuration for validation."""
    use_asar: bool = True
    use_asar_v2: bool = True
    use_asm: bool = True
    use_semantic: bool = True
    use_behavioral: bool = False
    asar_rom_type: Literal["lorom", "hirom", "exlorom", "exhirom"] = "lorom"
    extract_symbols: bool = True


@dataclass
class ModelConfig:
    """Configuration for model inference."""
    name: str = "nayru-7b-v1:latest"
    base_url: str = "http://localhost:11434"
    timeout_seconds: int = 60
    temperature: float = 0.7
    top_p: float = 0.8
    max_tokens: int = 512
    system_prompt: str = ""


@dataclass
class ReportConfig:
    """Configuration for report generation."""
    format: Literal["markdown", "json", "html"] = "markdown"
    include_samples: bool = True
    max_sample_length: int = 500
    include_errors: bool = True
    include_timing: bool = True
    output_path: Path | None = None


@dataclass
class EvalConfig:
    """Main evaluation configuration."""
    model: ModelConfig = field(default_factory=ModelConfig)
    prompts: PromptConfig = field(default_factory=PromptConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    concurrency: int = 5
    verbose: bool = False

    @classmethod
    def from_yaml(cls, path: Path) -> "EvalConfig":
        """Load configuration from YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalConfig":
        """Create configuration from dictionary."""
        model_data = data.get("model", {})
        prompts_data = data.get("prompts", {})
        validation_data = data.get("validation", {})
        report_data = data.get("report", {})

        # Convert paths
        if "templates_path" in prompts_data and prompts_data["templates_path"]:
            prompts_data["templates_path"] = Path(prompts_data["templates_path"])
        if "output_path" in report_data and report_data["output_path"]:
            report_data["output_path"] = Path(report_data["output_path"])

        return cls(
            model=ModelConfig(**model_data) if model_data else ModelConfig(),
            prompts=PromptConfig(**prompts_data) if prompts_data else PromptConfig(),
            validation=ValidationConfig(**validation_data) if validation_data else ValidationConfig(),
            report=ReportConfig(**report_data) if report_data else ReportConfig(),
            concurrency=data.get("concurrency", 5),
            verbose=data.get("verbose", False),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "model": {
                "name": self.model.name,
                "base_url": self.model.base_url,
                "timeout_seconds": self.model.timeout_seconds,
                "temperature": self.model.temperature,
                "top_p": self.model.top_p,
                "max_tokens": self.model.max_tokens,
                "system_prompt": self.model.system_prompt,
            },
            "prompts": {
                "categories": self.prompts.categories,
                "templates_path": str(self.prompts.templates_path) if self.prompts.templates_path else None,
                "custom_prompts": self.prompts.custom_prompts,
                "max_prompts_per_category": self.prompts.max_prompts_per_category,
            },
            "validation": {
                "use_asar": self.validation.use_asar,
                "use_asar_v2": self.validation.use_asar_v2,
                "use_asm": self.validation.use_asm,
                "use_semantic": self.validation.use_semantic,
                "use_behavioral": self.validation.use_behavioral,
                "asar_rom_type": self.validation.asar_rom_type,
                "extract_symbols": self.validation.extract_symbols,
            },
            "report": {
                "format": self.report.format,
                "include_samples": self.report.include_samples,
                "max_sample_length": self.report.max_sample_length,
                "include_errors": self.report.include_errors,
                "include_timing": self.report.include_timing,
                "output_path": str(self.report.output_path) if self.report.output_path else None,
            },
            "concurrency": self.concurrency,
            "verbose": self.verbose,
        }

    def to_yaml(self, path: Path) -> None:
        """Save configuration to YAML file."""
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)
