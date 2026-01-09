# Expert Model Improvements Plan

*Generated: 2026-01-07*
*Focus: Triforce MoE, training pipelines, tool loops, AFS integration*

## Current State Analysis

### Training Data Export Infrastructure

**Existing Capabilities:**
- `claude_export.py` - Exports Claude Code logs to TrainingSample JSONL
- `gemini_export.py` - Exports Gemini CLI sessions
- `codex_export.py` - Exports Codex CLI sessions
- Quality scoring via `QualityScorer` with ELECTRA discriminator
- Redaction of sensitive data (API keys, paths, etc.)
- Preserves tool call context

**What's Working:**
- Comprehensive log parsing for all three major AI tools
- Unified `TrainingSample` format
- Quality filtering with configurable thresholds
- Tool context preservation (inputs + outputs)

### Orchestration Infrastructure

**Simple Orchestrator** (`tools/orchestrator.py`):
- Basic wrapper around `ollama.chat()`
- No tool support
- No AFS access
- Single-turn only

**Full MoE Orchestrator** (`src/afs/moe/orchestrator.py`):
- Gemini-powered planning
- Triforce expert dispatch (din, nayru, farore)
- Basic tools: assemble, disassemble, read_file, write_file
- MCP integration via `claude mcp call` subprocess
- Dependency-aware execution plan

**Gaps Identified:**
1. Local models have no tool loop
2. No unified interface for local vs cloud models
3. Training export doesn't capture real-time quality signals
4. No AFS context access for local models
5. No active learning / sample selection

---

## Improvement Proposals

### 1. Unified Agent Harness with Tool Loop

Create a proper agentic runtime that gives ANY model (local or cloud) the same tool access.

```python
class AgentHarness:
    """Unified runtime for local and cloud models with tool access."""

    def __init__(
        self,
        model: str | ModelConfig,  # "nayru-v5:latest" or "gemini-2.0-flash"
        tools: list[Tool],
        context_root: Path = Path("~/.context"),
        max_iterations: int = 10,
        verbose: bool = False,
    ):
        self.model = self._resolve_model(model)
        self.tools = {t.name: t for t in tools}
        self.context = ContextLoader(context_root)
        self.history = []

    async def run(self, prompt: str) -> AgentResult:
        """Execute agent loop until completion or max iterations."""

        # Load relevant context
        context = await self.context.load_relevant(prompt)

        for i in range(self.max_iterations):
            # Get model response
            response = await self._generate(prompt, context, self.history)

            # Check for tool calls
            if tool_calls := self._extract_tool_calls(response):
                # Execute tools
                results = await self._execute_tools(tool_calls)

                # Add to history
                self.history.append({"role": "assistant", "content": response})
                self.history.append({"role": "tool", "results": results})

                # Continue loop
                continue

            # No tool calls = final response
            return AgentResult(
                response=response,
                history=self.history,
                tool_calls=self._all_tool_calls(),
            )

        return AgentResult(
            response="Max iterations reached",
            history=self.history,
            error="max_iterations",
        )
```

**Key Features:**
- Same interface for Ollama, Gemini, Anthropic, OpenAI
- Tool definitions in a model-agnostic format
- Automatic context loading from AFS
- History tracking for training export

### 2. AFS Tool Definitions

Create tools that give models access to the AFS ecosystem:

```python
AFS_TOOLS = [
    Tool(
        name="read_context",
        description="Read a file from AFS context",
        parameters={
            "path": {"type": "string", "description": "Path relative to context root"}
        },
        handler=read_context_handler,
    ),
    Tool(
        name="write_scratchpad",
        description="Write to scratchpad for working memory",
        parameters={
            "filename": {"type": "string"},
            "content": {"type": "string"},
        },
        handler=write_scratchpad_handler,
    ),
    Tool(
        name="ws_find",
        description="Find projects in workspace",
        parameters={"query": {"type": "string"}},
        handler=ws_find_handler,
    ),
    Tool(
        name="grep_codebase",
        description="Search code with ripgrep",
        parameters={
            "pattern": {"type": "string"},
            "path": {"type": "string", "default": "."},
        },
        handler=grep_handler,
    ),
    Tool(
        name="run_shell",
        description="Execute shell command (sandboxed)",
        parameters={"command": {"type": "string"}},
        handler=shell_handler,
    ),
]

TRIFORCE_TOOLS = AFS_TOOLS + [
    Tool(
        name="assemble",
        description="Assemble 65816 code with asar",
        parameters={"code": {"type": "string"}},
        handler=asar_handler,
    ),
    Tool(
        name="yaze_debug",
        description="Query YAZE emulator state",
        parameters={
            "command": {"type": "string"},
            "args": {"type": "object", "default": {}},
        },
        handler=yaze_mcp_handler,
    ),
    Tool(
        name="alttp_lookup",
        description="Look up ALTTP RAM addresses, sprites, etc.",
        parameters={"query": {"type": "string"}},
        handler=alttp_knowledge_handler,
    ),
]
```

### 3. Training Data Pipeline Improvements

**Auto-Export from Agent Runs:**

```python
class TrainingExportHook:
    """Hook to auto-export high-quality agent interactions."""

    def __init__(
        self,
        output_dir: Path,
        min_quality: float = 0.6,
        domains: list[str] = ["asm65816", "snes", "alttp"],
    ):
        self.scorer = QualityScorer()
        self.output_dir = output_dir
        self.min_quality = min_quality
        self.domains = domains

    async def on_agent_complete(self, result: AgentResult) -> None:
        """Called when agent completes a task."""

        # Convert to training samples
        samples = self._result_to_samples(result)

        # Score and filter
        for sample in samples:
            score = self.scorer.score(sample)
            if score.overall >= self.min_quality:
                # Check domain relevance
                if self._is_relevant_domain(sample):
                    self._append_to_pool(sample, score)

    def _append_to_pool(self, sample: TrainingSample, score: QualityScore):
        """Append to domain-specific training pool."""
        domain = sample.domain
        pool_path = self.output_dir / f"{domain}_pool.jsonl"

        sample._metadata["quality_score"] = score.overall
        sample._metadata["export_timestamp"] = datetime.now().isoformat()

        with pool_path.open("a") as f:
            f.write(json.dumps(sample.to_dict()) + "\n")
```

**Active Learning Sampler:**

```python
class ActiveLearningSampler:
    """Select high-value samples for training."""

    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2"):
        self.embedder = SentenceTransformer(embedding_model)
        self.known_samples = []

    def select_samples(
        self,
        candidates: list[TrainingSample],
        k: int = 100,
        strategy: str = "diverse",  # or "uncertain" or "hybrid"
    ) -> list[TrainingSample]:
        """Select k samples that would most improve training."""

        if strategy == "diverse":
            # Maximize coverage of embedding space
            return self._select_diverse(candidates, k)
        elif strategy == "uncertain":
            # Select where model is least confident
            return self._select_uncertain(candidates, k)
        else:
            # Hybrid: 50% diverse, 50% uncertain
            diverse = self._select_diverse(candidates, k // 2)
            uncertain = self._select_uncertain(candidates, k // 2)
            return diverse + uncertain
```

### 4. Hybrid Routing (Local + Cloud)

Route queries to the best model based on complexity and latency requirements:

```python
class HybridRouter:
    """Route queries to local or cloud models based on requirements."""

    def __init__(
        self,
        local_models: dict[str, str],   # intent -> ollama model
        cloud_fallback: str = "gemini-2.0-flash",
        complexity_threshold: float = 0.7,
    ):
        self.local = local_models
        self.cloud = cloud_fallback
        self.classifier = QueryClassifier()

    async def route(self, query: str) -> tuple[str, str]:
        """Return (model_type, model_id) for query."""

        # Classify intent and complexity
        intent = self.classifier.classify_intent(query)
        complexity = self.classifier.estimate_complexity(query)

        # Simple queries go to local experts
        if complexity < self.complexity_threshold:
            if local_model := self.local.get(intent):
                return ("local", local_model)

        # Complex queries go to cloud
        return ("cloud", self.cloud)

    async def generate_with_fallback(
        self,
        query: str,
        tools: list[Tool],
    ) -> AgentResult:
        """Generate with automatic fallback on local failure."""

        model_type, model_id = await self.route(query)

        try:
            harness = AgentHarness(model_id, tools)
            result = await harness.run(query)

            # Validate result quality
            if model_type == "local" and not self._is_quality_acceptable(result):
                # Fallback to cloud
                harness = AgentHarness(self.cloud, tools)
                result = await harness.run(query)
                result.metadata["fallback"] = True

            return result

        except Exception as e:
            if model_type == "local":
                # Fallback to cloud
                harness = AgentHarness(self.cloud, tools)
                return await harness.run(query)
            raise
```

### 5. Model Evaluation Framework

**A/B Testing Infrastructure:**

```python
class ModelABTest:
    """Run A/B tests between models."""

    def __init__(
        self,
        model_a: str,
        model_b: str,
        test_cases: list[TestCase],
        metrics: list[str] = ["quality", "latency", "cost"],
    ):
        self.model_a = model_a
        self.model_b = model_b
        self.test_cases = test_cases
        self.metrics = metrics
        self.harness = EvaluationHarness()

    async def run(self) -> ABTestResult:
        """Run test and return comparison."""

        results_a = []
        results_b = []

        for case in self.test_cases:
            # Run both models
            a = await self._run_model(self.model_a, case)
            b = await self._run_model(self.model_b, case)

            results_a.append(a)
            results_b.append(b)

        # Compute metrics
        return ABTestResult(
            model_a=self.model_a,
            model_b=self.model_b,
            metrics=self._compute_metrics(results_a, results_b),
            winner=self._determine_winner(results_a, results_b),
            samples=len(self.test_cases),
        )
```

**Triforce Expert Evaluation:**

```python
TRIFORCE_EVAL_SUITE = {
    "nayru": [
        # Code generation tests
        {"query": "Write DMA transfer to VRAM", "expected_ops": ["REP", "LDA", "STA"]},
        {"query": "Read controller input", "expected_ops": ["LDA", "$4218"]},
        {"query": "Play sound effect", "expected_ops": ["JSL", "SPC"]},
    ],
    "din": [
        # Optimization tests (before/after pairs)
        {"before": "LDA #$00\nSTA $10", "expected": "STZ $10"},
        {"before": "LDA $10\nCLC\nADC #$01\nSTA $10", "expected": "INC $10"},
    ],
    "farore": [
        # Bug detection tests
        {"code": "REP #$20\nLDA $10,x\n; BUG: no SEP before STA", "expected_bug": "mode mismatch"},
    ],
    "veran": [
        # Hardware knowledge tests
        {"query": "What is $2100?", "expected": "INIDISP"},
        {"query": "What is $420B?", "expected": "DMA"},
    ],
}
```

---

## Implementation Roadmap

### Phase 1: Agent Harness (Week 1-2)

1. Create `AgentHarness` class with tool loop
2. Implement model abstraction (Ollama, Gemini, Anthropic)
3. Create AFS tool definitions
4. Add TrainingExportHook

**Files to Create:**
- `src/afs/agent/harness.py` - Core agent runtime
- `src/afs/agent/tools.py` - Tool definitions
- `src/afs/agent/models.py` - Model abstraction
- `src/afs/agent/hooks.py` - Export hooks

### Phase 2: Training Pipeline (Week 2-3)

1. Integrate auto-export into orchestrator
2. Create active learning sampler
3. Build domain classifier for samples
4. Set up nightly training data aggregation

**Files to Modify:**
- `src/afs/training/pipeline.py` - Add auto-export
- `src/afs/active_learning/sampler.py` - Active learning

### Phase 3: Hybrid Routing (Week 3-4)

1. Implement HybridRouter
2. Add complexity estimation
3. Create fallback logic
4. Add latency/cost tracking

**Files to Create:**
- `src/afs/moe/hybrid_router.py`

### Phase 4: Evaluation (Week 4-5)

1. Build A/B testing framework
2. Create Triforce evaluation suite
3. Automate weekly model evals
4. Dashboard for tracking progress

**Files to Create:**
- `src/afs/evaluation/ab_test.py`
- `src/afs/evaluation/triforce_suite.py`
- `scripts/run_weekly_eval.py`

---

## CLI Interface

Proposed commands:

```bash
# Run agent with tool access
afs agent run --model nayru-v5:latest --prompt "Write DMA code" --tools triforce

# Export training data
afs training export --source claude --output ~/training/claude_exports.jsonl

# Run A/B test
afs eval ab-test --model-a nayru-v5:latest --model-b gemini-2.0-flash --suite asm_generation

# Check model quality
afs eval triforce --model veran-v1:latest --suite hardware_knowledge

# Aggregate training pools
afs training aggregate --domains asm65816,snes,alttp --output combined.jsonl
```

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Nayru code compilation rate | ~70% | 90% |
| Din optimization savings | ~10% | 20% |
| Farore bug detection | ~40% | 70% |
| Veran SNES accuracy | 30% | 70% |
| Training samples/week | ~0 | 100 |
| Local model usage | 5% | 50% |

---

## Dependencies

- `ollama` - Local model inference
- `google-genai` - Gemini API
- `anthropic` - Claude API (optional)
- `sentence-transformers` - Embedding for active learning
- `asar` - 65816 assembler

---

## Implementation Status

### Completed (Phase 1)

✅ **Agent Module Created** (`src/afs/agent/`)

| File | Purpose | Status |
|------|---------|--------|
| `__init__.py` | Package exports | ✅ Done |
| `models.py` | Model abstraction (Ollama, Gemini) | ✅ Done |
| `tools.py` | Tool definitions (AFS + Triforce) | ✅ Done |
| `harness.py` | Agent runtime with tool loop | ✅ Done |
| `hooks.py` | Training export hooks | ✅ Done |

**Features Implemented:**
- `ModelConfig` with presets for Triforce experts (din, nayru, farore, veran)
- `OllamaBackend` and `GeminiBackend` with unified interface
- 7 AFS tools (read_context, write_scratchpad, ws_find, grep_codebase, run_shell, read_file, write_file)
- 3 Triforce tools (assemble, yaze_debug, alttp_lookup)
- `AgentHarness` with iterative tool loop (max 10 iterations)
- `TrainingExportHook` with quality scoring and domain detection
- OpenAI/Gemini tool format conversion

**Usage:**
```python
from afs.agent import AgentHarness, TRIFORCE_TOOLS, create_training_hook

# With training auto-export
hook = create_training_hook(min_quality=0.7)
harness = AgentHarness("nayru-v5:latest", tools=TRIFORCE_TOOLS)
harness.add_hook(hook)

async with harness:
    result = await harness.run("Write a DMA transfer routine")
```

### Next Steps

1. [ ] Integrate agent harness with existing MoE orchestrator
2. [ ] Add hybrid routing (local + cloud fallback)
3. [ ] Build evaluation suite for Triforce experts
4. [ ] Create CLI commands (`afs agent run`, `afs eval`)
5. [ ] Add active learning sampler for training data selection
