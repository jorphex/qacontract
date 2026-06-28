import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

# ── Palette ──────────────────────────────────────────────
bg_color = '#080808'
surface_color = '#0e0e0e'
text_primary = '#e5e5e5'
text_secondary = '#9ca3af'
grid_color = '#1d1d1d'
accent = '#f97316'
visible_curve = '#e5e5e5'
banked_curve = '#f97316'

# ── Game params ─────────────────────────────────────────-
floor = 5
max_prize = 200
duration = 100

# Baseline quadratic curve (same shape used for every offset reset)
def baseline(t, floor=floor, max_p=max_prize, duration=duration):
    if t <= 0:
        return floor
    if t >= duration:
        return max_p
    return floor + (max_p - floor) * (t / duration) ** 2

# Reigns: (start, end, holder, is_correct)
reigns = [
    (0, 25, 'Bob', True),
    (25, 55, 'Alice', False),
    (55, 80, 'Carol', True),
    (80, 100, 'Dave', False),
]

# ── Banked correct curve ─────────────────────────────────
# Correct hold time accumulates; wrong holds pause the bank.
banked_points = []
banked_time = 0.0
for start, end, holder, correct in reigns:
    steps = 80
    if correct:
        start_banked = banked_time
        for t in np.linspace(start, end, steps):
            banked_time = start_banked + (t - start)
            v = baseline(banked_time)
            banked_points.append((t, v))
    else:
        v = baseline(banked_time)
        for t in np.linspace(start, end, steps):
            banked_points.append((t, v))

banked_t, banked_v = zip(*banked_points)

# ── Figure setup ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(16, 9), facecolor=bg_color)
ax.set_facecolor(bg_color)

# ── Plot visible offset curves (what the contract shows) ─
for start, end, holder, correct in reigns:
    t = np.linspace(start, end, 150)
    v = [baseline(ti - start) for ti in t]
    ax.plot(t, v, color=visible_curve, linewidth=3.5,
            linestyle='-', alpha=0.85, zorder=3)

    # Endpoint dot
    end_val = baseline(end - start)
    ax.plot(end, end_val, 'o', color=bg_color, markersize=12,
            markeredgecolor=visible_curve, markeredgewidth=2.5, zorder=5)

# ── Plot banked correct curve (hidden mechanic) ──────────
ax.plot(banked_t, banked_v, color=banked_curve, linewidth=5,
        linestyle='--', alpha=0.9, zorder=4, label='Banked value')

# ── Floor and max reference lines ────────────────────────
ax.axhline(y=floor, color=grid_color, linewidth=2.5, linestyle='-', zorder=1)
ax.axhline(y=max_prize, color=grid_color, linewidth=2, linestyle='--', alpha=0.6, zorder=1)
ax.text(96, max_prize + 2, 'MAX', ha='right', va='bottom', color=text_secondary,
        fontsize=13, fontweight='bold', alpha=0.9)

# ── Vertical reset drops ─────────────────────────────────
for i in range(1, len(reigns)):
    prev_start, prev_end, prev_holder, prev_correct = reigns[i - 1]
    prev_val = baseline(prev_end - prev_start)
    ax.plot([prev_end, prev_end], [floor, prev_val], color='white',
            linestyle=':', linewidth=2.5, alpha=0.7, zorder=2)
    ax.annotate('', xy=(prev_end, floor + 0.5), xytext=(prev_end, prev_val - 0.5),
                arrowprops=dict(arrowstyle='->', color='white', lw=2.5, alpha=0.85))

# ── Winner annotation ────────────────────────────────────
last_correct = None
for start, end, holder, correct in reigns:
    if correct:
        last_correct = (start, end, holder)

if last_correct:
    l_start, l_end, l_holder = last_correct
    l_banked_val = None
    for t, v in banked_points:
        if abs(t - l_end) < 0.01:
            l_banked_val = v
            break
    if l_banked_val is None:
        l_banked_val = baseline(sum(e - s for s, e, _, c in reigns if c and e <= l_end))

    ax.plot([l_end, l_end], [floor, l_banked_val], color=accent,
            linestyle='--', linewidth=2.5, alpha=0.9, zorder=4)
    ax.plot([l_end, 102], [l_banked_val, l_banked_val], color=accent,
            linestyle='--', linewidth=2.5, alpha=0.9, zorder=4)

    ax.annotate(
        f'{l_holder} wins ${int(round(l_banked_val))}',
        xy=(l_end, l_banked_val), xytext=(l_end - 28, l_banked_val + 30),
        fontsize=22, fontweight='bold', color=accent,
        ha='center', va='bottom',
        arrowprops=dict(arrowstyle='->', color=accent, lw=3),
        zorder=5,
    )

# ── Final holder annotation ─────────────────────────────-
f_start, f_end, f_holder, f_correct = reigns[-1]
f_val = baseline(f_end - f_start)
if not f_correct:
    ax.annotate(
        f'{f_holder}: wrong, no prize',
        xy=(f_end, f_val), xytext=(f_end - 6, f_val + 22),
        fontsize=16, fontweight='bold', color=text_secondary,
        ha='center', va='bottom',
        arrowprops=dict(arrowstyle='->', color=text_secondary, lw=2),
        zorder=5,
    )

# ── Wrong-hold annotation ────────────────────────────────
ax.annotate(
    'Wrong = not banked',
    xy=(40, baseline(40 - 25)), xytext=(30, 75),
    fontsize=16, fontweight='bold', color=text_secondary,
    ha='center', va='bottom',
    arrowprops=dict(arrowstyle='->', color=text_secondary, lw=2),
    zorder=5,
)

# ── Title ────────────────────────────────────────────────
ax.set_title(
    'King of the Hill v4',
    fontsize=34, fontweight='bold', color=text_primary, pad=20,
)

# ── Legend ───────────────────────────────────────────────
legend_elements = [
    mpatches.Patch(facecolor='none', edgecolor=visible_curve,
        linestyle='-', linewidth=3.5, label='Visible curve'),
    mpatches.Patch(facecolor='none', edgecolor=banked_curve,
        linestyle='--', linewidth=4, label='Banked value'),
]

legend = ax.legend(
    handles=legend_elements,
    loc='upper left',
    bbox_to_anchor=(0.04, 0.98),
    fontsize=14,
    frameon=True,
    facecolor=surface_color,
    edgecolor=grid_color,
    labelspacing=0.7,
)
for text in legend.get_texts():
    text.set_color(text_primary)
    text.set_fontweight('bold')

# ── Rules box ────────────────────────────────────────────
rules_box = mpatches.FancyBboxPatch(
    (0.04, 0.56), 0.44, 0.26,
    transform=ax.transAxes,
    boxstyle='round,pad=0.01',
    facecolor=surface_color,
    edgecolor=grid_color,
    linewidth=1.5,
    zorder=5,
)
ax.add_patch(rules_box)

rules_text = """RULES
• Steals reset the visible curve
• Correct hold time banks; wrong does not
• Last correct reign wins banked value"""
ax.text(
    0.05, 0.80, rules_text,
    transform=ax.transAxes,
    fontsize=16, fontweight='bold', color=text_primary,
    va='top', ha='left',
    zorder=6,
)

# ── Axes config ──────────────────────────────────────────
ax.set_xlim(0, duration + 4)
ax.set_ylim(0, max_prize + 7)

ax.set_xlabel('Game Time', fontsize=18, fontweight='bold', color=text_primary, labelpad=14)
ax.set_ylabel('Prize Amount ($)', fontsize=18, fontweight='bold', color=text_primary, labelpad=14)

ax.tick_params(colors=text_primary, labelsize=15)

ax.yaxis.grid(True, linestyle='--', alpha=0.25, color=grid_color)
ax.xaxis.grid(True, linestyle='--', alpha=0.15, color=grid_color)

# Spines
for spine in ['top', 'right']:
    ax.spines[spine].set_visible(False)
for spine in ['bottom', 'left']:
    ax.spines[spine].set_color(grid_color)
    ax.spines[spine].set_linewidth(1.0)

# ── Save ─────────────────────────────────────────────────
fig.subplots_adjust(left=0.09, right=0.96, top=0.90, bottom=0.12)
output_path = Path(__file__).parent / 'king_of_the_hill_chart.png'
plt.savefig(output_path, dpi=150, facecolor=bg_color, edgecolor='none')
print(f'saved {output_path}')