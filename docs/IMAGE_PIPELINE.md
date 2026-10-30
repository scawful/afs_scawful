# OpenAI image pipeline

Python 3.11+ on macOS/Linux; no SDK installation needed. Defaults are
`gpt-image-2.5-sunburst`, `quality=max`, `size=3840x2160`, one PNG per nonblank
prompt line. 4K output is experimental according to OpenAI's documentation.

## Run

1. Claim your subscription's API credit benefit in
   [OpenAI billing](https://platform.openai.com/settings/organization/billing/overview).
   Use a project key belonging to that organization. Complete organization
   verification if the image model requires it. Keep the key in `OPENAI_API_KEY`;
   never paste it into a prompt file or commit it. Optional `OPENAI_ORG_ID` and
   `OPENAI_PROJECT_ID` select explicit organization/project headers.
2. Write `prompts.txt`, one prompt per line. Preview without network requests:

   ```sh
   python3 scripts/generate_images.py prompts.txt --out ~/Pictures/openai-images/run-01
   ```

3. Generate one pilot image, inspect its usage/cost, then run the remainder:

   ```sh
   python3 scripts/generate_images.py prompts.txt --out ~/Pictures/openai-images/run-01 --limit 1 --execute
   python3 scripts/generate_images.py prompts.txt --out ~/Pictures/openai-images/run-01 --execute
   ```

Numbered PNGs and `manifest.json` share one output directory. Completed images
are hash-checked and skipped. Changed prompts/settings require a new directory.
The manifest retains prompts, settings, actual usage, estimated charges,
request IDs and output hashes. A generation timeout stops with an unresolved
request: inspect API usage before starting a new run, because blindly retrying
may pay twice. Explicit rate-limit errors use bounded exponential backoff;
`credit_balance_exhausted` stops immediately.

## Batch

Use a different directory from a standard run. Submission returns immediately;
the server has a 24-hour completion window. No background polling is installed.

```sh
python3 scripts/generate_images.py prompts.txt --out ~/Pictures/openai-images/batch-01 --batch --execute
python3 scripts/generate_images.py --out ~/Pictures/openai-images/batch-01 --collect --execute
```

Collection exits `3` while pending, `0` when collected successfully, or `1` for
an error. Run collection later if pending. Results are mapped by `custom_id`,
not output order. Partial successes are saved even if other requests fail;
failed requests are never automatically resubmitted. Collection needs only
the manifest, not the original prompt file.

If submission stops without a recorded batch ID, inspect the dashboard using
the saved `input_file_id` and `afs_image_run` metadata before resubmitting.
An output-directory lock prevents concurrent writers. Batch results stream to
disk one file/line at a time. Successful base64 duplicates are removed after
PNG, usage and error receipts are durable; unresolved response spools remain.

## Costs and credits

The running figure printed after each image is **image output cost**, at
$30/million output tokens for standard requests or $15/million for Batch.
The manifest separately estimates total uncached token charges using
$5/million text-input and $8/million image-input tokens (halved for Batch).
Missing usage is marked unknown, never zero. These are token-rate estimates;
the billing dashboard is authoritative. There is no promised $0.40/image price
and this script is not an account-wide spending cap. `--limit` bounds how many
new images are requested in an invocation.

Subscription credits expire at the billing-cycle boundary. **If purchased
credits remain, API requests continue consuming those after free credits run
out**; `credit_balance_exhausted` is not a free-credit-only spending guard.
The script cannot verify your subscription grant or remaining free balance.

For Oracle, generated art is a reference candidate. Importing pixels into
SNES tiles/palettes or changing shared graphics remains a separate workflow.

## Verification and sources

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_image_pipeline.py
```

Sources checked 2026-10-30:
[API credits](https://developers.openai.com/api/docs/guides/chatgpt-api-credits),
[Sunburst model](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst),
[Images endpoint](https://developers.openai.com/api/reference/resources/images/methods/generate),
[Batch](https://developers.openai.com/api/docs/guides/batch).
