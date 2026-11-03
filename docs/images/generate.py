#!/usr/bin/env python3
"""Regenerate learner diagrams for docs/linking-explained.md. Docs only."""
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle, FancyArrowPatch

OUT = Path(__file__).resolve().parent
BG, INK, MUTED, LINE = "#FBFBFA", "#1A1A1A", "#5A5A56", "#D6D6D1"
RAW, OBERON, PYTHON, CPU, BAD = "#1D4ED8", "#047857", "#C2410C", "#6D28D9", "#B91C1C"
SOFT, CARD, AMMT, LT = "#F3F3F0", "#FFFFFF", "#1E3A5F", "#3730A3"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "text.color": INK,
    "figure.facecolor": BG,
    "savefig.facecolor": BG,
})


def rounded(ax, x, y, w, h, fc=CARD, ec=LINE, lw=1.4, r=0.08, z=2):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                       facecolor=fc, edgecolor=ec, linewidth=lw, zorder=z)
    ax.add_patch(p)
    return p


def save(fig, name):
    fig.savefig(OUT / name, dpi=160, bbox_inches="tight", pad_inches=0.35)
    plt.close(fig)
    print("wrote", name)


def blank(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    fig.subplots_adjust(0, 0, 1, 1)
    return fig, ax


def overview():
    fig, ax = blank(13.6, 8.6)
    ax.text(0.45, 8.25, "Blink3 after linking — two modules, one instruction memory",
            fontsize=17, fontweight="bold", va="top")
    ax.text(0.45, 7.72,
            "The compiler left a placeholder jump. A loader is supposed to patch it so LightToggle can call Toggle.",
            fontsize=11, color=MUTED, va="top")

    rounded(ax, 0.4, 4.55, 12.8, 2.85, fc=SOFT, ec=LINE, r=0.06)
    ax.text(0.6, 7.15, "instruction memory   (what the CPU fetches)", fontsize=9.5, color=MUTED)

    rounded(ax, 0.6, 4.75, 5.7, 2.15, fc="#E8EEF6", ec=AMMT, lw=1.8, r=0.07)
    ax.text(0.8, 6.6, "AMemoryMappedToggle", fontsize=13, fontweight="bold", color=AMMT)
    ax.text(0.8, 6.22, "module 1     base 0x1000", fontsize=10, color=MUTED)
    rounded(ax, 0.85, 4.95, 5.2, 1.05, fc=CARD, ec=OBERON, lw=1.5, r=0.05)
    ax.text(1.05, 5.7, "PROCEDURE Toggle*     starts at 0x1000", fontsize=11, fontweight="bold", color=OBERON)
    ax.text(1.05, 5.22, "entry[2] = 0    saves R15, flips light, returns with BT R15",
            fontsize=9.5, color=MUTED)

    rounded(ax, 7.3, 4.75, 5.7, 2.15, fc="#EEEDF7", ec=LT, lw=1.8, r=0.07)
    ax.text(7.5, 6.6, "LightToggle  (Blink3)", fontsize=13, fontweight="bold", color=LT)
    ax.text(7.5, 6.22, "module 2     base 0x1048     entry 0x1048", fontsize=10, color=MUTED)
    rounded(ax, 7.55, 4.95, 5.2, 1.05, fc=CARD, ec=PYTHON, lw=1.5, r=0.05)
    ax.text(7.75, 5.7, "the call site    MMT.Toggle", fontsize=11, fontweight="bold")
    ax.text(7.75, 5.22, "lives at 0x108C  (word 17 of this module)", fontsize=9.5, color=MUTED)

    ax.annotate("", xy=(3.4, 5.55), xytext=(8.3, 5.35),
                arrowprops=dict(arrowstyle="-|>", color=OBERON, lw=2.4,
                                connectionstyle="arc3,rad=0.18"))
    ax.text(5.35, 6.95, "real Oberon jumps here", fontsize=9, color=OBERON, fontweight="bold",
            ha="center")
    ax.annotate("", xy=(8.6, 5.95), xytext=(10.4, 5.55),
                arrowprops=dict(arrowstyle="-|>", color=PYTHON, lw=2.2,
                                connectionstyle="arc3,rad=-0.35"))
    ax.text(9.85, 6.95, "Python jumps here (wrong)", fontsize=9, color=PYTHON, fontweight="bold",
            ha="center")

    cards = [
        (0.4, RAW, "1. Raw compiler word", "0xF7102011",
         "Not a real jump yet.\nPacked: module 1, proc 2,\nchain displacement 17."),
        (4.8, OBERON, "2. Real Oberon Modules.Mod", "0xF7FFFFDC",
         "BL always, offset −36.\nJumps to 0x1000 — Toggle.\nSaves return addr in R15."),
        (9.2, PYTHON, "3. Python loader today", "0xF7FFFFF0",
         "BL always, offset −16.\nJumps to 0x1050 — MOV R0, 0\ninside LightToggle. Wrong."),
    ]
    for x, color, title, hexword, body in cards:
        rounded(ax, x, 0.25, 4.05, 3.95, fc=CARD, ec=color, lw=1.8, r=0.08)
        ax.add_patch(Rectangle((x, 4.02), 4.05, 0.18, facecolor=color, edgecolor="none", zorder=3))
        ax.text(x + 0.22, 3.7, title, fontsize=11.5, fontweight="bold", color=color)
        ax.text(x + 0.22, 3.05, hexword, fontsize=18, fontweight="bold", fontfamily="DejaVu Sans Mono")
        ax.text(x + 0.22, 0.5, body, fontsize=11, color=MUTED, va="bottom")
    save(fig, "linking-overview.png")


def decode():
    fig, ax = blank(13.6, 8.8)
    ax.text(0.45, 8.45, "How to read 0xF7102011  —  a placeholder, not a jump",
            fontsize=17, fontweight="bold", va="top")
    ax.text(0.45, 7.95,
            "The compiler packs three numbers into the 24-bit offset field. The loader unpacks them, computes a real offset, and rewrites the word.",
            fontsize=11, color=MUTED, va="top")

    ax.text(0.45, 7.45, "0xF7102011   as bit fields", fontsize=12, fontweight="bold")
    bits = [
        (0.45, 1.85, "31–28", "1111", "F3 + link\nv = 1", RAW),
        (2.40, 1.85, "27–24", "0111", "cond =\nalways", MUTED),
        (4.35, 1.85, "23–20", "0001", "mno = 1\nwhich import", RAW),
        (6.30, 2.55, "19–12", "0000 0010", "pno = 2\nwhich export", RAW),
        (8.95, 3.85, "11–0", "0000 0001 0001", "disp = 17\nchain to next", MUTED),
    ]
    y, h = 5.35, 1.85
    for x, w, title, bits_s, meaning, color in bits:
        rounded(ax, x, y, w, h, fc=CARD, ec=color, lw=1.5, r=0.06)
        ax.text(x + w / 2, y + h - 0.32, title, ha="center", fontsize=9, color=MUTED)
        ax.text(x + w / 2, y + h - 0.82, bits_s, ha="center", fontsize=12,
                fontfamily="DejaVu Sans Mono", fontweight="bold")
        ax.text(x + w / 2, y + 0.22, meaning, ha="center", va="bottom", fontsize=10)

    rounded(ax, 0.45, 3.55, 12.7, 1.55, fc=SOFT, ec=LINE, r=0.06)
    ax.text(0.7, 4.78, "How the compiler packed it   (ORG.Call, imported case)", fontsize=11, fontweight="bold")
    ax.text(0.7, 4.28, "Put3(BL, 7,  ((−x.r) × 100H + x.a) × 1000H  +  pc − fixorgP)",
            fontsize=12.5, fontfamily="DejaVu Sans Mono")
    ax.text(0.7, 3.75,
            "x.r = −1  (first import)     x.a = 2  (Toggle’s export number)     pc − fixorgP = 17"
            "     →  0xF7000000 | 0x102011  =  0xF7102011",
            fontsize=10.5, color=MUTED)

    for x, color, title, hexword, lines in [
        (0.45, OBERON, "Real Modules.Mod", "0xF7FFFFDC",
         "offset = (0x1000 − 0x108C − 4) / 4  =  −36\n"
         "24-bit two’s complement:  0xFFFFDC\n"
         "PC′ = 0x108C + 4 + (−36)×4  =  0x1000\n"
         "Lands on Toggle.  Correct."),
        (7.05, PYTHON, "Python module_loader.py", "0xF7FFFFF0",
         "looks up MT slot 0 (empty dummy)\n"
         "ent = 0,  code = 0,  dest = 8\n"
         "offset = (8 − 0x44 − 4) / 4  =  −16\n"
         "PC′ = 0x108C + 4 + (−16)×4  =  0x1050   (MOV R0, 0)"),
    ]:
        rounded(ax, x, 0.2, 6.15, 3.1, fc=CARD, ec=color, lw=1.8, r=0.08)
        ax.add_patch(Rectangle((x, 3.12), 6.15, 0.18, facecolor=color, edgecolor="none", zorder=3))
        ax.text(x + 0.25, 2.75, title, fontsize=13, fontweight="bold", color=color)
        ax.text(x + 0.25, 2.18, hexword, fontsize=18, fontweight="bold", fontfamily="DejaVu Sans Mono")
        ax.text(x + 0.25, 0.4, lines, fontsize=11, color=MUTED, va="bottom")
    save(fig, "bl-placeholder-decode.png")


def fixup_sites():
    fig, ax = blank(13.8, 9.6)
    ax.text(0.4, 9.25, "Every fixup in linked Blink3 — raw → real Oberon → Python",
            fontsize=17, fontweight="bold", va="top")
    ax.text(0.4, 8.72,
            "P-list = procedure calls (BL).   D-list = data accesses (load of the static base).   T-list is empty (no type descriptors).",
            fontsize=11, color=MUTED, va="top")

    headers = ["Site (linked addr)", "Raw compiler word", "Real Oberon Modules.Mod", "Python loader today", "Bug in"]
    xs = [0.5, 3.35, 6.55, 9.75, 12.55]
    for x, h in zip(xs, headers):
        ax.text(x, 8.28, h, fontsize=9.5, fontweight="bold", color=MUTED)
    ax.plot([0.4, 13.4], [8.12, 8.12], color=LINE, lw=1.0)

    rows = [
        ("#FFF7ED", PYTHON,
         "P-list  ·  the call\n0x108C  LightToggle\nMMT.Toggle",
         "0xF7102011\nBL  mno=1  pno=2\ndisp=17  (chain)",
         "0xF7FFFFDC\nBL always  off=−36\n→ 0x1000 Toggle",
         "0xF7FFFFF0\nBL always  off=−16\n→ 0x1050 MOV R0,0",
         "Python\nloader"),
        (CARD, OBERON,
         "D-list  ·  LightToggle\n0x1094  word 19\n0x1068  word 8\n0x1054  word 3",
         "0x8D00000B / 05 / 03\nLDW R13,[R0,disp]\nmno=0  (this module)",
         "0x8DC00008  all three\nLDW R13,[R12, 8]\nMT[2] → vars at 0x70",
         "0x8DC00008  all three\nsame rewrite for globals\nwhen module_id = 2",
         "—\n(globals OK)"),
        (CARD, OBERON,
         "D-list  ·  AMMT\n0x1034  word 13\n0x100C  word 3",
         "0x8D00000A / 03\nLDW R13,[R0,disp]\nmno=0  (this module)",
         "0x8DC00004  both\nLDW R13,[R12, 4]\nMT[1] → vars at 0x50",
         "0x8DC00004  both\nsame rewrite for globals\nwhen module_id = 1",
         "—\n(globals OK)"),
        (SOFT, MUTED,
         "T-list  ·  types\nnone",
         "fixorgT = 0\nno type descriptors\nin either module",
         "loop never runs",
         "loop never runs",
         "—"),
    ]
    y = 7.95
    heights = [1.7, 1.85, 1.7, 1.45]
    for h, (bg, accent, a, b, c, d, e) in zip(heights, rows):
        rounded(ax, 0.4, y - h, 13.0, h - 0.12, fc=bg, ec=LINE, r=0.05)
        ax.text(0.55, y - 0.22, a, fontsize=10, va="top", fontfamily="DejaVu Sans Mono")
        ax.text(3.35, y - 0.22, b, fontsize=10, va="top", fontfamily="DejaVu Sans Mono", color=RAW)
        ax.text(6.55, y - 0.22, c, fontsize=10, va="top", fontfamily="DejaVu Sans Mono", color=OBERON)
        ax.text(9.75, y - 0.22, d, fontsize=10, va="top", fontfamily="DejaVu Sans Mono",
                color=PYTHON if accent == PYTHON else MUTED)
        ax.text(12.55, y - 0.22, e, fontsize=10, va="top", fontweight="bold",
                color=PYTHON if accent == PYTHON else MUTED)
        y -= h

    ax.text(0.4, 0.28,
            "Takeaway: data (D-list) fixups for these two modules rewrite the way real Oberon would. The P-list (the BL) is the one the Python loader gets wrong.",
            fontsize=11.5)
    save(fig, "fixup-sites.png")


def two_bugs():
    fig, ax = blank(13.6, 8.4)
    ax.text(0.45, 8.05, "Two bugs, two sides of the wall", fontsize=17, fontweight="bold", va="top")
    ax.text(0.45, 7.52,
            "Linking happens on the host, in Python, before the FPGA ever sees the program.  BL/R15 happens later, in Chisel, on every taken branch.",
            fontsize=11, color=MUTED, va="top")

    rounded(ax, 0.4, 1.85, 5.95, 5.2, fc=CARD, ec=PYTHON, lw=2.0, r=0.1)
    ax.text(0.7, 6.65, "HOST  ·  Python loader", fontsize=15, fontweight="bold", color=PYTHON)
    ax.text(0.7, 6.18, "tools/module_loader.py", fontsize=11, fontfamily="DejaVu Sans Mono", color=MUTED)
    ax.text(0.7, 5.55, "Job: walk the P / D / T fixup chains and\nrewrite placeholders into real offsets.",
            fontsize=11.5, va="top")
    ax.text(0.7, 4.55, "What it gets wrong", fontsize=12, fontweight="bold", color=PYTHON)
    ax.text(0.7, 4.15,
            "The imported BL. MT slot is off by one,\nthe entry table is never indexed, and the\naddress used to compute the offset is the\nunlinked one.",
            fontsize=11, color=MUTED, va="top")
    ax.text(0.7, 2.7, "What it gets right", fontsize=12, fontweight="bold", color=OBERON)
    ax.text(0.7, 2.3, "D-list globals become\nLDW R13, [R12, mod.num × 4].",
            fontsize=11, color=MUTED, va="top")

    rounded(ax, 7.25, 1.85, 5.95, 5.2, fc=CARD, ec=CPU, lw=2.0, r=0.1)
    ax.text(7.55, 6.65, "FPGA  ·  Chisel CPU", fontsize=15, fontweight="bold", color=CPU)
    ax.text(7.55, 6.18, "src/main/scala/gcd/CPUSubset0.scala",
            fontsize=11, fontfamily="DejaVu Sans Mono", color=MUTED)
    ax.text(7.55, 5.55, "Job: when a taken branch has v=1, write\nR15 = PC+4, then jump.",
            fontsize=11.5, va="top")
    ax.text(7.55, 4.55, "What it gets wrong", fontsize=12, fontweight="bold", color=CPU)
    ax.text(7.55, 4.15,
            "It never writes R15. Format bits 110/111\ncorrectly pick register vs offset. The\nlink bit is ignored.",
            fontsize=11, color=MUTED, va="top")
    ax.text(7.55, 2.7, "What it gets right", fontsize=12, fontweight="bold", color=OBERON)
    ax.text(7.55, 2.3, "BT R15 (v=0) returns to whatever\nR15 already holds.",
            fontsize=11, color=MUTED, va="top")

    ax.annotate("", xy=(7.25, 4.45), xytext=(6.35, 4.45),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.8))
    ax.text(6.8, 4.62, "final_system.code", fontsize=8.5, ha="center", color=MUTED)

    rounded(ax, 0.4, 0.25, 12.8, 1.3, fc=SOFT, ec=LINE, r=0.08)
    ax.text(0.7, 0.88,
            "Fixing only the CPU would still jump to the wrong place.\n"
            "Fixing only the loader would jump to Toggle and never come back.",
            fontsize=13, va="center")
    save(fig, "two-bugs.png")


def timeline():
    fig, ax = blank(13.6, 10.4)
    ax.text(0.45, 10.05, "Was BL / R15 ever working?    Short answer: no.",
            fontsize=17, fontweight="bold", va="top")
    ax.text(0.45, 9.5,
            "Every branch path in CPUSubset0 writes the PC and nothing else. No commit in this repo has ever stored PC+4 into R15.",
            fontsize=11, color=MUTED, va="top")

    events = [
        ("2025-03-01", "8b35428", CPU,
         "“implement branch to register (v=1 / link)”",
         "Implemented: if the 24-bit offset is 0, jump to Rc.\n"
         "Not implemented: write PC+4 into R15.\n"
         "The title says “link”. The code does “branch to register”."),
        ("2025-03-01", "c79f8c8", MUTED,
         "“hopeful test for the pre-post instructions / preamble”",
         "The program is SUB / STW R15 / MOV / LDW R15 / ADD / BT R15.\n"
         "R15 is already filled by the trampoline (MOV R15, halt).\n"
         "No BL instruction is in the test at all."),
        ("2025-03-01", "345cb92", CPU,
         "“fix preamble test” — format bits 110 vs 111",
         "Replaced off==0 with isBranchToReg / isBranchWithOffset.\n"
         "Decode is now correct for BT vs B-offset.\n"
         "Still no R15 write. Still silent on BL."),
        ("2025-03-01", "e5743c8", RAW,
         "“trivially modularized blink3”",
         "First program that actually emits BL (the call to Toggle).\n"
         "No BL test was added. Blink2 still returns with BT R15."),
        ("2026-11-03", "54604c5", BAD,
         "“ignore unfinished Blink3 test”",
         "Comment on the ignored test: “BL does not save R15,\n"
         "IMEM too small, linker still rough.” Named, then skipped."),
    ]
    ax.plot([0.75, 0.75], [0.45, 8.95], color=LINE, lw=2.6, zorder=1)
    y = 8.75
    for date, sha, color, title, body in events:
        ax.add_patch(Circle((0.75, y), 0.13, facecolor=color, edgecolor=CARD, lw=2.2, zorder=3))
        ax.text(1.15, y + 0.02, f"{date}    {sha}", fontsize=10, color=MUTED,
                va="center", fontfamily="DejaVu Sans Mono")
        ax.text(5.55, y + 0.02, title, fontsize=12, fontweight="bold", va="center")
        ax.text(1.15, y - 0.45, body, fontsize=11, color=MUTED, va="top")
        y -= 1.65
    save(fig, "r15-timeline.png")


def hidden():
    fig, ax = blank(13.6, 9.2)
    ax.text(0.45, 8.85, "Why both bugs survived every green test",
            fontsize=17, fontweight="bold", va="top")
    ax.text(0.45, 8.32,
            "Each test was true for what it asked. Neither asked the question that would have failed.",
            fontsize=11, color=MUTED, va="top")

    rounded(ax, 0.35, 0.3, 6.35, 7.7, fc=CARD, ec=PYTHON, lw=1.9, r=0.1)
    ax.add_patch(Rectangle((0.35, 7.6), 6.35, 0.4, facecolor=PYTHON, edgecolor="none", zorder=3))
    ax.text(0.55, 7.8, "Python loader bug  —  wrong jump", fontsize=13,
            fontweight="bold", color="white", va="center", zorder=4)

    rounded(ax, 6.9, 0.3, 6.35, 7.7, fc=CARD, ec=CPU, lw=1.9, r=0.1)
    ax.add_patch(Rectangle((6.9, 7.6), 6.35, 0.4, facecolor=CPU, edgecolor="none", zorder=3))
    ax.text(7.1, 7.8, "Chisel CPU bug  —  R15 never saved", fontsize=13,
            fontweight="bold", color="white", va="center", zorder=4)

    left = [
        ("Per-module .code files look “linked”",
         "Fixup rewrites the BL to an F7 encoding, so a dump of Blink3test.code no longer shows 0xF7102011. It looks like a finished relative jump. Nobody compared the jump target to Toggle’s address."),
        ("No linker diff table",
         "final_system.code is a dump of words. There is no column for “raw / should become / actually became / jumps to”."),
        ("System-image test was ignored",
         "When it timed out waiting for LED writes, CI marked it ignore (54604c5) instead of asserting the patched BL."),
    ]
    right = [
        ("Prologue test pre-loads R15",
         "Setup does MOV R15, halt. The test program is SUB / STW R15 / MOV / LDW R15 / BT R15. R15 is already the return address. BL is never executed. The test still passes."),
        ("BT test uses C7000002",
         "That encoding is 110v with v=0: branch to register, no link. It checks that R1 stays 0xBEEF. It never reads R15."),
        ("Blink2 does not use BL",
         "Blink2 inlines the toggle. It returns with BT R15 to the trampoline’s halt address. Hardware can blink forever with R15-save missing."),
    ]

    def column(items, x):
        import textwrap
        y = 7.2
        for title, body in items:
            ax.text(x, y, title, fontsize=12, fontweight="bold", va="top", zorder=4)
            wrapped = "\n".join(textwrap.wrap(body, width=46))
            ax.text(x, y - 0.42, wrapped, fontsize=10.5, color=MUTED, va="top", zorder=4)
            y -= 2.25

    column(left, 0.6)
    column(right, 7.15)
    save(fig, "hidden-bugs.png")


if __name__ == "__main__":
    overview()
    decode()
    fixup_sites()
    two_bugs()
    timeline()
    hidden()
    print("done")
