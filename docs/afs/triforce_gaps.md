# Triforce Expert Knowledge Gap Analysis

*Generated: 2026-01-07T19:44:02.391048*


## Farore

**Overall:** 1/5 tests passed (19.0%)

### Knowledge Gaps

#### detect_mode_mismatch
- **Score:** 0.00
- **Missing concepts:** mode, 16-bit, 8-bit, mismatch, size
- **Response preview:** `  #_05F8A9: REP #$20

  #_05F8AB: LDA.b $12
  #_05F8AD: STA.b $14

  #_05F8AF: SEP #$20

; =========================================================
...`

#### detect_stack_corruption
- **Score:** 0.00
- **Missing concepts:** stack, PHA, PLA, imbalance, unmatched
- **Response preview:** `  #_018E5F: PHX
  #_018E60: PHY

  #_018E61: JSR .main

  #_018E64: STZ.w $0329

  #_018E67: JSL PaletteFilter_Main

  #_018E6B: LDY.b #$1F
  #_018E6D...`

#### detect_register_clobber
- **Score:** 0.20
- **Missing concepts:** clobber, preserve, PHY, PLY
- **Response preview:** `The issue with the Y register being corrupted in your routine is likely due to an overlap between the stack and data segments. The JSR instruction, wh...`

#### detect_dma_error
- **Score:** 0.00
- **Missing concepts:** $4305, $4306, length, size, count
- **Response preview:** `DMA Transfer Issue (Module 01)

Your DMA transfer is not occurring as expected. The source and destination addresses are set up correctly, but the dat...`

### Most Commonly Missing Concepts

- `size` (missing 2x)
- `mode` (missing 1x)
- `16-bit` (missing 1x)
- `8-bit` (missing 1x)
- `mismatch` (missing 1x)