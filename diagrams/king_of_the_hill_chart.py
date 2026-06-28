import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

# ── Palette (kept from design agent) ─────────────────────
bg_color = '#0f0f0f'
surface_color = '#1a1a1a'
text_primary = '#f0f0f0'
text_secondary = '#a0a0a0'
grid_color = '#2a2a2a'
accent_winner = '#4ade80'

player_colors = {
    'Bob':   '#fb923c',
    'Alice': '#60a5fa',
    'Carol': '#4ade80',
    'Dave':  '#c084fc',
}

# ── Game params ──────────────────────────────────────────
floor = 5
max_prize = 200
duration = 100

# Quadratic growth toward max_prize at game expiry
def curve_value(start_t, current_t, end_t=duration, floor=floor, max_p=max_prize):
    elapsed = current_t - start_t
    dur = end_t - start_t
    if elapsed <= 0 or dur <= 0:
        return floor
    p = elapsed / dur
    return floor + (max_p - floor) * (p ** 2)

# Reigns: (start, end, holder, is_correct)
reigns = [
    (0, 25, 'Bob', True),
    (25, 55, 'Alice', False),
    (55, 80, 'Carol', True),
    (80, 100, 'Dave', False),
]

# ── Figure setup ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(16, 9), facecolor=bg_color)
ax.set_facecolor(bg_color)

# ── Plot actual reign curves ─────────────────────────────
for start, end, holder, correct in reigns:
    t = np.linspace(start, end, 150)
    v = [curve_value(start, ti) for ti in t]
    linestyle = '-' if correct else '--'
    linewidth = 6.0 if correct else 4.0
    alpha = 1.0 if correct else 0.65
    ax.plot(t, v, color=player_colors[holder], linewidth=linewidth,
            linestyle=linestyle, alpha=alpha, zorder=3,
            label=f'{holder} holds{" (correct)" if correct else " (wrong)"}')

    # End dot
    end_val = curve_value(start, end)
    ax.plot(end, end_val, 'o', color=player_colors[holder], markersize=14,
            markeredgecolor='white', markeredgewidth=2, zorder=5)

# ── Floor and max reference lines ────────────────────────
ax.axhline(y=floor, color=grid_color, linewidth=2.5, linestyle='-', zorder=1)
ax.axhline(y=max_prize, color=grid_color, linewidth=2, linestyle='--', alpha=0.6, zorder=1)
ax.text(5, max_prize + 0.8, 'MAX PRIZE IF HELD TO EXPIRY',
        ha='left', va='bottom', color=text_secondary,
        fontsize=12, fontweight='bold', alpha=0.9)

# ── Vertical reset drops ─────────────────────────────────
for i in range(1, len(reigns)):
    prev_start, prev_end, prev_holder, prev_correct = reigns[i - 1]
    prev_val = curve_value(prev_start, prev_end)

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
    l_val = curve_value(l_start, l_end)

    # Highlight winning reign
    win_t = np.linspace(l_start, l_end, 100)
    win_v = [curve_value(l_start, ti) for ti in win_t]
    ax.plot(win_t, win_v, color=player_colors[l_holder], linewidth=12,
            alpha=0.2, zorder=1)

    # Prize lines
    ax.plot([l_end, l_end], [floor, l_val], color=accent_winner,
            linestyle='--', linewidth=2.5, alpha=0.9, zorder=4)
    ax.plot([l_end, 102], [l_val, l_val], color=accent_winner,
            linestyle='--', linewidth=2.5, alpha=0.9, zorder=4)

    ax.annotate(
        f'{l_holder} wins ${int(round(l_val))}\n(last correct reign\nstolen at t={l_end})',
        xy=(l_end, l_val), xytext=(l_end - 24, l_val + 5),
        fontsize=19, fontweight='bold', color=accent_winner,
        ha='center', va='bottom',
        arrowprops=dict(arrowstyle='->', color=accent_winner, lw=3),
        zorder=5,
    )

# ── Final holder annotation ──────────────────────────────
f_start, f_end, f_holder, f_correct = reigns[-1]
f_val = curve_value(f_start, f_end)

if not f_correct:
    ax.annotate(
        f'{f_holder} holds to expiry\nbut wins nothing (wrong)',
        xy=(f_end, f_val), xytext=(f_end - 18, f_val - 2),
        fontsize=15, fontweight='bold', color=player_colors[f_holder],
        ha='center', va='top',
        arrowprops=dict(arrowstyle='->', color=player_colors[f_holder], lw=2),
        zorder=5,
    )

# ── Out-of-ammo annotation ───────────────────────────────
ammo_t = 67
ammo_val = curve_value(55, ammo_t)
ax.plot(ammo_t, ammo_val, 'x', color='#ff4444', markersize=22,
        markeredgewidth=5, zorder=6)
ax.annotate(
    "Bob's shot tx reverts\nbecause out of ammo",
    xy=(ammo_t, ammo_val), xytext=(ammo_t - 28, ammo_val + 35),
    fontsize=14, fontweight='bold', color=player_colors['Bob'],
    ha='center', va='bottom',
    arrowprops=dict(arrowstyle='-', color=player_colors['Bob'], lw=2.5),
    zorder=6,
)

# ── Title ────────────────────────────────────────────────
ax.set_title(
    'King of the Hill v4: Last Correct Reign Wins',
    fontsize=30, fontweight='bold', color=text_primary, pad=20,
)

# ── Legend (upper left, above Bob's curve) ───────────────
legend_elements = []
for p, c in player_colors.items():
    legend_elements.append(mpatches.Patch(color=c, label=p, alpha=1.0))
legend_elements.append(mpatches.Patch(facecolor='none', edgecolor=text_primary,
    linestyle='-', linewidth=3, label='Correct'))
legend_elements.append(mpatches.Patch(facecolor='none', edgecolor=text_primary,
    linestyle='--', linewidth=2, label='Wrong'))

legend = ax.legend(
    handles=legend_elements,
    loc='upper left',
    bbox_to_anchor=(0.04, 0.50),
    fontsize=13,
    frameon=True,
    facecolor=surface_color,
    edgecolor=grid_color,
    labelspacing=0.6,
)
for text in legend.get_texts():
    text.set_color(text_primary)
    text.set_fontweight('bold')

# ── Rules box (upper left, above Bob's curve) ────────────
rules_box = mpatches.FancyBboxPatch(
    (0.04, 0.54), 0.32, 0.22,
    transform=ax.transAxes,
    boxstyle='round,pad=0.01',
    facecolor=surface_color,
    edgecolor=grid_color,
    linewidth=1.5,
    zorder=5,
)
ax.add_patch(rules_box)

rules_text = """RULES
• Each steal resets prize to floor
• Wrong answers can steal the hill
• Last CORRECT reign wins
• Prize = growth when that reign ended"""
ax.text(
    0.05, 0.65, rules_text,
    transform=ax.transAxes,
    fontsize=14, fontweight='bold', color=text_primary,
    va='center', ha='left',
    zorder=6,
)

# ── Axes config ──────────────────────────────────────────
ax.set_xlim(0, duration + 4)
ax.set_ylim(0, max_prize + 20)
ax.set_yticks(np.arange(0, max_prize + 21, 20))

ax.set_xlabel('Game Time', fontsize=18, fontweight='bold', color=text_primary, labelpad=14)
ax.set_ylabel('Prize Amount ($)', fontsize=18, fontweight='bold', color=text_primary, labelpad=14)

ax.tick_params(colors=text_primary, labelsize=14)

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