# Training Cheatsheet (2026)

## LoRA Hyperparameters (Optimized)
- **Rank (r):** 64 for 7B, 128 for 14B+.
- **Alpha:** 2x Rank (e.g., 256 for r=128).
- **Target Modules:** `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj`.
- **Learning Rate:** `1e-4` for synthetic data, `5e-5` for human-curated.
- **Batch Size:** 4-8 per 24GB VRAM.

## Synthetic Data Recipes
- **Assembly Optimization:** [Vanilla Code] + [Constraint: "Reduce cycles by 10%"] -> [Optimized Code].
- **Bug Injection:** [Working Routine] + [Bug Type: "Off-by-one"] -> [Broken Routine].
- **Analysis:** [Binary Dump] + [ROM Map] -> [Natural Language Explanation].

## Hardware Targets
- **Local Mac:** MLX for LoRA fine-tuning (M2/M3 Max with 64GB+ RAM).
- **Vast.ai:** RTX 4090 (24GB) or H100 (80GB) for larger batch sizes.

## Resource Management (macOS)
Before starting a local training run or heavy inference session (LMStudio):
1. **Quarantine background processes:** Run `~/src/lab/scripts/ai_resource_manager.sh on`.
2. This will `SIGSTOP` non-essential background apps like `cloudd` and `SearchParty`.
3. **Safety:** The script explicitly **protects** active agents (`claude`, `node`, `gemini`, `codex`) and your IDE/Terminal tree from being paused.
4. **Monitor:** Check the `AI: HIGH` status in Sketchybar.
5. **Release:** After the session, run `~/src/lab/scripts/ai_resource_manager.sh off`.


