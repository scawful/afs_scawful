# Eval Report: models/gemini-3-pro-preview

**Generated:** 2026-01-02 22:42:01
**Duration:** 26.2s

## Summary

| Metric | Value |
|--------|-------|
| Total Prompts | 20 |
| Passed | 0 (0.0%) |
| Failed | 20 |
| Avg Score | 0.19 |
| Avg Latency | 6316ms |
| Avg Tokens/s | 3.1 |

## By Category

| Category | Total | Passed | Pass Rate | Avg Score |
|----------|-------|--------|-----------|-----------|
| bug_fixing | 2 | 0 | 0.0% | 0.25 |
| code_explanation | 2 | 0 | 0.0% | 0.10 |
| code_generation | 7 | 0 | 0.0% | 0.30 |
| documentation | 2 | 0 | 0.0% | 0.10 |
| explanation | 4 | 0 | 0.0% | 0.10 |
| memory_qa | 2 | 0 | 0.0% | 0.10 |
| optimization | 1 | 0 | 0.0% | 0.25 |

## Failed Samples

### 1. code_generation

**Prompt:** Write a 65816 routine that clears $7E0E20 and $7E0E22 and returns.

**Response:**
```

```

**Errors:** No code found

### 2. code_generation

**Prompt:** Write a 65816 routine that stores A to $7E0010 and returns with RTL.

**Response:**
```

```

**Errors:** No code found

### 3. code_generation

**Prompt:** Write a routine that loads X with #$0010, loops decrementing X to zero, then RTS.

**Response:**
```

```

**Errors:** No code found

### 4. code_generation

**Prompt:** Write a routine that sets the carry flag if $7E0010 is zero.

**Response:**
```

```

**Errors:** No code found

### 5. code_generation

**Prompt:** Write a routine that saves A and X on the stack, calls SubRoutine, restores, then RTL.

**Response:**
```
PHA
PHX
JSL SubRoutine
PLX
PLA
RTL
```

**Errors:** (Elabel_not_found): Label 'SubRoutine' wasn't found. [JSL SubRoutine]

### 6. code_generation

**Prompt:** Write a routine that increments $7E0F00 and returns.

**Response:**
```

```

**Errors:** No code found

### 7. code_generation

**Prompt:** Create a hook stub at $00F000 that JSLs to NewRoutine and returns to $00F004.

**Response:**
```

```

**Errors:** No code found

### 8. bug_fixing

**Prompt:** Fix the bug in this routine so it preserves X and Y.

**Response:**
```

```

**Errors:** No code found

### 9. optimization

**Prompt:** Optimize this routine for fewer bytes.

**Response:**
```

```

**Errors:** No code found

### 10. bug_fixing

**Prompt:** Fix the missing return in this routine.

**Response:**
```

```

**Errors:** No code found
