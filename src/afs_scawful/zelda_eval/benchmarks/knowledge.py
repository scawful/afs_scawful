"""
Pre-defined knowledge benchmarks for 65816, ALTTP, and SNES.
"""

from .base import BenchmarkCase, BenchmarkCategory, BenchmarkSuite, Difficulty


KNOWLEDGE_65816_CASES = [
    BenchmarkCase(
        id="65816_addressing_direct",
        category=BenchmarkCategory.KNOWLEDGE_65816,
        prompt="Explain the difference between direct page addressing (LDA $10) and absolute addressing (LDA $0010) in 65816 assembly.",
        difficulty=Difficulty.EASY,
        tags=["addressing", "direct-page"],
    ),
    BenchmarkCase(
        id="65816_addressing_indirect",
        category=BenchmarkCategory.KNOWLEDGE_65816,
        prompt="Explain the difference between LDA $7E0010 and LDA [$00] in 65816 assembly. When would you use each?",
        difficulty=Difficulty.MEDIUM,
        tags=["addressing", "indirect"],
    ),
    BenchmarkCase(
        id="65816_bank_crossing",
        category=BenchmarkCategory.KNOWLEDGE_65816,
        prompt="Write a 65816 routine that safely copies 0x1000 bytes from $7E8000 to $7F0000 using MVN, handling the bank boundary correctly.",
        difficulty=Difficulty.HARD,
        tags=["mvn", "bank", "block-move"],
        tool_hints=["validate_asm"],
    ),
    BenchmarkCase(
        id="65816_stack_frame",
        category=BenchmarkCategory.KNOWLEDGE_65816,
        prompt="Write a 65816 subroutine that uses the stack to create a 16-byte local variable frame, demonstrates proper PHD/PLD usage, and restores state on exit.",
        difficulty=Difficulty.HARD,
        tags=["stack", "frame", "phd", "pld"],
        tool_hints=["validate_asm"],
    ),
    BenchmarkCase(
        id="65816_interrupt_handler",
        category=BenchmarkCategory.KNOWLEDGE_65816,
        prompt="Write a proper NMI interrupt handler for the SNES that saves all registers, handles both 8-bit and 16-bit modes, and restores state correctly.",
        difficulty=Difficulty.EXPERT,
        tags=["interrupt", "nmi", "snes"],
        tool_hints=["validate_asm"],
    ),
    BenchmarkCase(
        id="65816_rep_sep",
        category=BenchmarkCategory.KNOWLEDGE_65816,
        prompt="Explain REP and SEP instructions. What do REP #$30 and SEP #$20 do? Why is tracking the M and X flags critical?",
        difficulty=Difficulty.MEDIUM,
        tags=["flags", "rep", "sep", "processor-status"],
    ),
    BenchmarkCase(
        id="65816_long_addressing",
        category=BenchmarkCategory.KNOWLEDGE_65816,
        prompt="Compare JSR, JSL, RTS, and RTL. When must you use JSL/RTL vs JSR/RTS?",
        difficulty=Difficulty.MEDIUM,
        tags=["jumps", "subroutines", "banks"],
    ),
]

KNOWLEDGE_ALTTP_CASES = [
    BenchmarkCase(
        id="alttp_link_position",
        category=BenchmarkCategory.KNOWLEDGE_ALTTP,
        prompt="What RAM addresses store Link's X and Y position in A Link to the Past? Include both low and high bytes.",
        difficulty=Difficulty.EASY,
        tags=["ram", "link", "position"],
    ),
    BenchmarkCase(
        id="alttp_game_mode",
        category=BenchmarkCategory.KNOWLEDGE_ALTTP,
        prompt="Explain the ALTTP game mode system. What RAM address controls the main game mode, and what are the key mode values (overworld, dungeon, menu, etc)?",
        difficulty=Difficulty.MEDIUM,
        tags=["ram", "game-mode", "state-machine"],
    ),
    BenchmarkCase(
        id="alttp_sprite_system",
        category=BenchmarkCategory.KNOWLEDGE_ALTTP,
        prompt="Describe the ALTTP sprite system. How are sprites stored in RAM, what are the key tables ($0D00, $0E20, etc), and how does the game iterate through active sprites?",
        difficulty=Difficulty.HARD,
        tags=["sprites", "ram", "oam"],
    ),
    BenchmarkCase(
        id="alttp_dma_transfer",
        category=BenchmarkCategory.KNOWLEDGE_ALTTP,
        prompt="Write a routine that performs a DMA transfer to upload 0x800 bytes of tile data to VRAM address $4000, following ALTTP's patterns.",
        difficulty=Difficulty.HARD,
        tags=["dma", "vram", "tiles"],
        tool_hints=["validate_asm", "read_memory"],
    ),
    BenchmarkCase(
        id="alttp_submodule",
        category=BenchmarkCategory.KNOWLEDGE_ALTTP,
        prompt="Explain the ALTTP submodule system. How do $10 (main module) and $11 (submodule) work together? Give examples of module/submodule pairs.",
        difficulty=Difficulty.MEDIUM,
        tags=["modules", "state-machine", "control-flow"],
    ),
    BenchmarkCase(
        id="alttp_ancilla",
        category=BenchmarkCategory.KNOWLEDGE_ALTTP,
        prompt="What are ancillae in ALTTP? How do they differ from sprites? Name some examples and explain their RAM layout.",
        difficulty=Difficulty.HARD,
        tags=["ancillae", "projectiles", "effects"],
    ),
    BenchmarkCase(
        id="alttp_room_loading",
        category=BenchmarkCategory.KNOWLEDGE_ALTTP,
        prompt="Describe how ALTTP loads a dungeon room. What data is read, how are objects/sprites spawned, and what RAM is initialized?",
        difficulty=Difficulty.EXPERT,
        tags=["rooms", "loading", "dungeons"],
    ),
]

KNOWLEDGE_SNES_CASES = [
    BenchmarkCase(
        id="snes_ppu_registers",
        category=BenchmarkCategory.KNOWLEDGE_SNES,
        prompt="Explain the SNES PPU registers $2100-$2106. What does each control and what are common initialization values?",
        difficulty=Difficulty.MEDIUM,
        tags=["ppu", "registers", "video"],
    ),
    BenchmarkCase(
        id="snes_hdma",
        category=BenchmarkCategory.KNOWLEDGE_SNES,
        prompt="Write an HDMA table and setup routine that creates a horizontal wavy effect on BG1 by modifying BG1HOFS each scanline.",
        difficulty=Difficulty.EXPERT,
        tags=["hdma", "effects", "bg-scroll"],
        tool_hints=["validate_asm", "assemble_and_run"],
    ),
    BenchmarkCase(
        id="snes_mode7",
        category=BenchmarkCategory.KNOWLEDGE_SNES,
        prompt="Explain Mode 7 on the SNES. What registers control it, how is the transformation matrix structured, and what are the limitations?",
        difficulty=Difficulty.HARD,
        tags=["mode7", "rotation", "scaling"],
    ),
    BenchmarkCase(
        id="snes_dma_channels",
        category=BenchmarkCategory.KNOWLEDGE_SNES,
        prompt="Explain the 8 DMA channels on the SNES. What registers configure each channel, and how do you initiate a transfer?",
        difficulty=Difficulty.MEDIUM,
        tags=["dma", "channels", "transfer"],
    ),
    BenchmarkCase(
        id="snes_vblank",
        category=BenchmarkCategory.KNOWLEDGE_SNES,
        prompt="What work must be done during VBlank on the SNES? Why is timing critical, and what happens if you exceed the VBlank window?",
        difficulty=Difficulty.MEDIUM,
        tags=["vblank", "timing", "nmi"],
    ),
    BenchmarkCase(
        id="snes_oam",
        category=BenchmarkCategory.KNOWLEDGE_SNES,
        prompt="Explain the SNES OAM (Object Attribute Memory) structure. How are sprites defined, what are the size limitations, and how is the high table used?",
        difficulty=Difficulty.HARD,
        tags=["oam", "sprites", "hardware"],
    ),
]


def get_knowledge_suite() -> BenchmarkSuite:
    """Get the complete knowledge benchmark suite."""
    return BenchmarkSuite(
        name="Zelda Knowledge Benchmarks",
        description="Tests knowledge of 65816 assembly, ALTTP internals, and SNES hardware",
        cases=KNOWLEDGE_65816_CASES + KNOWLEDGE_ALTTP_CASES + KNOWLEDGE_SNES_CASES,
    )


def get_65816_suite() -> BenchmarkSuite:
    """Get 65816-only benchmarks."""
    return BenchmarkSuite(
        name="65816 Assembly Knowledge",
        description="Tests knowledge of the 65816 processor and assembly language",
        cases=KNOWLEDGE_65816_CASES,
    )


def get_alttp_suite() -> BenchmarkSuite:
    """Get ALTTP-only benchmarks."""
    return BenchmarkSuite(
        name="ALTTP Internals Knowledge",
        description="Tests knowledge of A Link to the Past's internal systems",
        cases=KNOWLEDGE_ALTTP_CASES,
    )


def get_snes_suite() -> BenchmarkSuite:
    """Get SNES hardware benchmarks."""
    return BenchmarkSuite(
        name="SNES Hardware Knowledge",
        description="Tests knowledge of SNES hardware (PPU, DMA, etc)",
        cases=KNOWLEDGE_SNES_CASES,
    )
