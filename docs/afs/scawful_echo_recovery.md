# Scawful-Echo Recovery & Persona Restoration
**Date:** 2026-01-06
**Status:** Success

## Incident
The `scawful-echo` model was observed reverting to a generic, corporate AI persona (Gemma default) during local inference. It failed to recall context anchors (North Jersey, Oracle of Secrets) or maintain the specific "candid/dry" voice.

## Root Cause
The `Modelfile` for the model did not explicitly include the `SYSTEM` prompt containing the persona definition. The training data contained these prompts, but they were not enforced at the inference runtime layer in Ollama.

## Fix Implemented
1.  **Created `Modelfile.scawful`** in the project root.
2.  **Injected System Prompt:**
    ```dockerfile
    SYSTEM """
    you are scawful-echo, a voice distilled from justin's writing.
    style: lowercase, candid, dry humor, technical but casual
    context: north jersey, software engineer, oracle of secrets, yaze
    """
    ```
3.  **Rebuilt Model:** `ollama create scawful-echo -f Modelfile.scawful`

## Verification
*   **Prompt:** "How's the hacking going?"
*   **Result:** Correctly identified "Oracle" as the ROM hack, referenced 65816 ASM, and used the correct lowercase/casual styling.

## Prevention
*   Ensure the `SYSTEM` block is always part of the `Modelfile` generation process in the AFS pipeline.
*   Do not rely solely on fine-tuning data to carry the persona; enforce it at runtime.
