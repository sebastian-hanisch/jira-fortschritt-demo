"""Plotly-Abbildungen. Alle Achsen sind gesperrt (fixedrange), damit Touch-Geräte beim Scrollen nicht am Diagramm hängen bleiben."""

import numpy as np
import plotly.graph_objects as go

import jira_constants as C
from jira_algorithm import PAIR_SEP, natural_key

MAX_BARS = 30      # mehr Balken lassen sich nicht mehr lesen; die Tabelle darunter zeigt alle Gruppen


def lock_axes(fig):
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def _base(fig, height=360, legend_y=-0.2):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=legend_y), plot_bgcolor="rgba(0,0,0,0)")
    return lock_axes(fig)


def _pct_text(progress: float, weight: float, unit: str) -> str:
    return "ohne Gewicht" if np.isnan(progress) else f"{100 * progress:.0f} % · {weight:.0f} {unit}".replace(".", ",")


def build_progress_bars(stats, unit: str):
    """Ein Balken je Gruppe, Länge = Gewicht: erledigt (dunkel), durch Status angerechnet (hell), offen (grau). Beschriftung rechts: Fortschritt und Gewicht."""
    order = np.argsort(-stats.weight, kind="stable")[:MAX_BARS]
    order = sorted(order, key=lambda i: i)           # in der natürlichen Reihenfolge der Gruppen zeigen, nicht nach Gewicht
    labels = [stats.labels[i] for i in order]
    done = np.minimum(stats.done_weight[order], stats.credited[order])
    partial = np.maximum(stats.credited[order] - done, 0.0)
    rest = np.maximum(stats.weight[order] - done - partial, 0.0)
    prog = stats.progress[order]
    fig = go.Figure()
    for name, values, color in (("erledigt", done, C.COLOR_DONE), ("durch Status angerechnet", partial, C.COLOR_PARTIAL), ("offen", rest, C.COLOR_OPEN)):
        fig.add_trace(go.Bar(y=labels, x=values, orientation="h", name=name, marker_color=color, hovertemplate=f"%{{y}}<br>{name}: %{{x:.1f}} {unit}<extra></extra>"))
    top = float(max(stats.weight[order].max(), 1e-9)) if len(order) else 1.0
    for label, p, w in zip(labels, prog, stats.weight[order]):
        fig.add_annotation(x=w, y=label, text=" " + _pct_text(p, w, unit), showarrow=False, xanchor="left", font=dict(size=12))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(autorange="reversed", automargin=True)
    fig.update_xaxes(title_text=f"Gewicht ({unit})", range=[0, top * 1.6])
    return _base(fig, height=max(240, 34 * len(labels) + 130), legend_y=-0.45)      # Legende unter dem Achsentitel, auch auf schmalen Bildschirmen


def build_treemap(h):
    """Fläche = Gewicht, Farbe = Fortschritt (rot 0 %, gelb 50 %, grün 100 %). Ein Klick auf ein Epic zoomt hinein."""
    fig = go.Figure(go.Treemap(
        ids=list(h.ids), labels=list(h.labels), parents=list(h.parents), values=list(h.values), branchvalues="total",
        marker=dict(colors=list(h.progress), colorscale=C.COLOR_SCALE, cmin=0, cmax=1, colorbar=dict(title="Fortschritt", tickformat=".0%", nticks=5)),
        customdata=list(h.progress), texttemplate="%{label}<br>%{customdata:.0%}", hovertemplate="%{label}<br>Gewicht %{value:.1f}<br>Fortschritt %{customdata:.0%}<extra></extra>"))
    fig.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0))
    return fig


def build_heatmap(cross, row_dim: str, col_dim: str):
    """Fortschritt je Kombination zweier Ebenen; leere Felder bleiben leer, in den Feldern stehen Fortschritt und Gewicht."""
    pairs = [lbl.rsplit(PAIR_SEP, 1) for lbl in cross.labels]
    rows = sorted({p[0] for p in pairs}, key=natural_key)
    cols = sorted({p[1] for p in pairs}, key=natural_key)
    z = np.full((len(rows), len(cols)), np.nan)
    text = [["" for _ in cols] for _ in rows]
    for (r, c), p, w in zip(pairs, cross.progress, cross.weight):
        z[rows.index(r), cols.index(c)] = p
        text[rows.index(r)][cols.index(c)] = _pct_text(p, w, "").strip(" ·") if not np.isnan(p) else "–"
    fig = go.Figure(go.Heatmap(
        z=z, x=cols, y=rows, zmin=0, zmax=1, colorscale=C.COLOR_SCALE, text=text, texttemplate="%{text}", hoverongaps=False,
        colorbar=dict(title="Fortschritt", tickformat=".0%", nticks=5), hovertemplate=f"{row_dim}: %{{y}}<br>{col_dim}: %{{x}}<br>%{{text}}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", automargin=True)
    fig.update_xaxes(side="top")
    return _base(fig, height=max(240, 40 * len(rows) + 110))


def build_burnup(grid, scope, finished, unit: str):
    """Umfang (alle bis dahin erstellten Tickets) und erledigter Umfang über die Zeit. Nur Done zählt: der Statusverlauf liegt nicht vor."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=grid, y=scope, mode="lines", line=dict(color=C.COLOR_SCOPE, width=3, shape="hv"), name="Umfang (erstellt)",
                             hovertemplate=f"%{{x|%d.%m.%Y}}: %{{y:.1f}} {unit}<extra>Umfang</extra>"))
    fig.add_trace(go.Scatter(x=grid, y=finished, mode="lines", line=dict(color=C.COLOR_DONE, width=3, shape="hv"), name="erledigt",
                             hovertemplate=f"%{{x|%d.%m.%Y}}: %{{y:.1f}} {unit}<extra>erledigt</extra>"))
    fig.update_yaxes(title_text=f"Gewicht ({unit})", rangemode="tozero")
    return _base(fig)


def build_sensitivity(rows):
    """Gesamtfortschritt unter jeder Schema-Gewichtungs-Kombination; die Achse reicht fest von 0 bis 100 %."""
    schemes = list(dict.fromkeys(r["scheme"] for r in rows))
    fig = go.Figure()
    for mode, color in ((C.WEIGHT_POINTS, C.COLOR_DONE), (C.WEIGHT_COUNT, C.COLOR_SCOPE)):
        sel = {r["scheme"]: r["progress"] for r in rows if r["mode"] == mode}
        ys = [100 * sel[s] if not np.isnan(sel[s]) else None for s in schemes]
        fig.add_trace(go.Bar(x=schemes, y=ys, name=mode, marker_color=color, text=[f"{y:.0f} %".replace(".", ",") if y is not None else "–" for y in ys],
                             textposition="outside", hovertemplate="%{x}<br>" + mode + ": %{y:.1f} %<extra></extra>"))
    fig.update_layout(barmode="group")
    fig.update_yaxes(title_text="Gesamtfortschritt (%)", range=[0, 115])
    return _base(fig)
