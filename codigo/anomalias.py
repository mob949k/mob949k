#!/usr/bin/env python3
"""Detección de anomalías en tráfico de red SIMULADO + gráfico SVG animado.

Idea: la estadística sirve para encontrar lo que no encaja.
  1. Se genera tráfico sintético (ciclo diario + ruido) con picos y una caída inyectados.
  2. Se estima el comportamiento "normal" con una mediana móvil.
  3. Se mide qué tan lejos queda cada punto con el z-score modificado (basado en MAD),
     que, a diferencia de media y desviación estándar, no se deja arrastrar por los
     propios outliers (Iglewicz & Hoaglin: umbral típico 3.5).
  4. Se dibuja el resultado en assets/anomalias.svg.

Solo usa la librería estándar. Los datos son sintéticos (semilla fija, reproducibles).

Uso:
    python3 codigo/anomalias.py                  # escribe assets/anomalias.svg
    python3 codigo/anomalias.py salida.svg       # otra ruta
    python3 codigo/anomalias.py salida.svg --estatico   # sin animación (para vista previa)
"""
import math
import random
import sys
from pathlib import Path
from statistics import median
from xml.sax.saxutils import escape

# ---------------------------------------------------------------- datos
N = 120                      # muestras
SEMILLA = 949
UMBRAL = 3.5                 # |z modificado| > UMBRAL  =>  anomalía
VENTANA = 21                 # ventana de la mediana móvil (impar)
INYECTADAS = {27: +95, 58: +80, 59: +70, 76: -70, 93: +110}   # índice -> desviación


def generar_trafico():
    rng = random.Random(SEMILLA)
    serie = []
    for i in range(N):
        ciclo = 18 * math.sin(2 * math.pi * i / 60)       # patrón "diario"
        ruido = rng.gauss(0, 8)
        serie.append(100 + ciclo + ruido + INYECTADAS.get(i, 0))
    return serie


def base_movil(serie, ventana=VENTANA):
    """Mediana móvil centrada: estimación robusta de lo 'normal'."""
    m = ventana // 2
    return [median(serie[max(0, i - m): i + m + 1]) for i in range(len(serie))]


def detectar(serie):
    base = base_movil(serie)
    resid = [x - b for x, b in zip(serie, base)]
    med = median(resid)
    mad = median(abs(r - med) for r in resid)
    z = [0.6745 * (r - med) / mad for r in resid]          # z-score modificado
    banda = UMBRAL * mad / 0.6745                           # semiancho de la zona "normal"
    marcados = [i for i, v in enumerate(z) if abs(v) > UMBRAL]
    return base, banda, z, marcados


# ---------------------------------------------------------------- dibujo
W, H = 820, 280
ML, MR, MT, MB = 58, 26, 64, 46
PW, PH = W - ML - MR, H - MT - MB
BG, GRID, DIM, FG = "#0d1117", "#21262d", "#8b949e", "#c9d1d9"
VERDE, ROJO = "#00ff41", "#ff4d4d"
FUENTE = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono','DejaVu Sans Mono',monospace"
T = 11.0                     # duración del ciclo (s)
T_INICIO, T_DIBUJO = 0.4, 4.6


def construir_svg(serie, base, banda, marcados, estatico=False):
    lo = min(min(serie), min(b - banda for b in base)) - 10
    hi = max(max(serie), max(b + banda for b in base)) + 10
    X = lambda i: ML + PW * i / (N - 1)
    Y = lambda v: MT + PH * (1 - (v - lo) / (hi - lo))
    kt = lambda t: f"{min(max(t / T, 0), 1):.5f}"
    anim = (lambda s: "") if estatico else (lambda s: s)
    oculto = "" if estatico else ' opacity="0"'      # estado inicial de lo que aparece luego

    pts = [(X(i), Y(v)) for i, v in enumerate(serie)]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    # fracción de longitud recorrida por la línea en cada punto (para sincronizar marcadores)
    acum = [0.0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        acum.append(acum[-1] + math.hypot(x1 - x0, y1 - y0))
    frac = [a / acum[-1] for a in acum]

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="{FUENTE}" font-size="12" role="img" '
         f'aria-label="Gráfico de tráfico simulado con {len(marcados)} anomalías detectadas por z-score modificado">']
    o.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10" fill="{BG}" stroke="#30363d"/>')

    # título y leyenda
    o.append(f'<text x="{ML}" y="26" fill="{VERDE}">// detección de anomalías</text>')
    o.append(f'<text x="{ML}" y="44" fill="{DIM}">tráfico simulado (bytes/s) · z-score modificado (MAD) · umbral |z| &gt; {UMBRAL}</text>')
    o.append(f'<circle cx="{W - 190}" cy="22" r="4" fill="{VERDE}"/><text x="{W - 180}" y="26" fill="{DIM}">muestra</text>')
    o.append(f'<circle cx="{W - 110}" cy="22" r="4" fill="{ROJO}"/><text x="{W - 100}" y="26" fill="{DIM}">anomalía</text>')

    # rejilla y ejes
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        y = Y(v)
        o.append(f'<line x1="{ML}" y1="{y:.1f}" x2="{W - MR}" y2="{y:.1f}" stroke="{GRID}"/>')
        o.append(f'<text x="{ML - 8}" y="{y + 4:.1f}" fill="{DIM}" text-anchor="end">{v:.0f}</text>')
    for i in (0, 30, 60, 90, N - 1):
        o.append(f'<text x="{X(i):.1f}" y="{H - MB + 18}" fill="{DIM}" text-anchor="middle">{i}</text>')
    o.append(f'<text x="{W - MR}" y="{H - 8}" fill="{DIM}" text-anchor="end">t (muestras)</text>')

    # banda de comportamiento normal (mediana móvil ± umbral)
    arriba = " ".join(f"{X(i):.1f},{Y(b + banda):.1f}" for i, b in enumerate(base))
    abajo = " ".join(f"{X(i):.1f},{Y(b - banda):.1f}" for i, b in reversed(list(enumerate(base))))
    o.append(f'<polygon points="{arriba} {abajo}" fill="{VERDE}" fill-opacity="0.07"/>')

    # la serie, que se "dibuja" sola
    o.append(f'<path d="{d}" pathLength="1" fill="none" stroke="{VERDE}" stroke-width="1.8" '
             f'stroke-linejoin="round" stroke-linecap="round" '
             + ('' if estatico else 'stroke-dasharray="1" stroke-dashoffset="1"')
             + '>'
             + anim(f'<animate attributeName="stroke-dashoffset" values="1;1;0;0" '
                    f'keyTimes="0;{kt(T_INICIO)};{kt(T_INICIO + T_DIBUJO)};1" dur="{T}s" repeatCount="indefinite"/>')
             + '</path>')

    # anomalías: aparecen cuando la línea llega a ellas y laten
    for i in marcados:
        t = T_INICIO + T_DIBUJO * frac[i]
        x, y = pts[i]
        ap = anim(f'<animate attributeName="opacity" values="0;1" keyTimes="0;{kt(t)}" '
                  f'calcMode="discrete" dur="{T}s" repeatCount="indefinite"/>')
        pulso = anim(f'<animate attributeName="r" values="5;16" dur="1.4s" repeatCount="indefinite"/>'
                     f'<animate attributeName="stroke-opacity" values="0.9;0" dur="1.4s" repeatCount="indefinite"/>')
        o.append(f'<g{oculto}>'
                 f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="none" stroke="{ROJO}">{pulso}</circle>'
                 f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{ROJO}"/>{ap}</g>')

    # resumen final
    t_fin = T_INICIO + T_DIBUJO + 0.3
    resumen = (f'<text x="{ML + 6}" y="{H - 8}" fill="{ROJO}">'
               f'&gt; {len(marcados)} anomalías en {N} muestras</text>')
    o.append(f'<g{oculto}>{resumen}'
             + anim(f'<animate attributeName="opacity" values="0;1" keyTimes="0;{kt(t_fin)}" '
                    f'calcMode="discrete" dur="{T}s" repeatCount="indefinite"/>') + '</g>')
    o.append('</svg>')
    return "".join(o)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    estatico = "--estatico" in sys.argv
    salida = Path(args[0]) if args else Path(__file__).resolve().parent.parent / "assets" / "anomalias.svg"

    serie = generar_trafico()
    base, banda, z, marcados = detectar(serie)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(construir_svg(serie, base, banda, marcados, estatico), encoding="utf-8")

    inyectadas = sorted(INYECTADAS)
    print(f"muestras: {N} | marcadas: {len(marcados)} -> {marcados}")
    print(f"inyectadas: {inyectadas}")
    print(f"aciertos: {len(set(marcados) & set(inyectadas))}/{len(inyectadas)} | "
          f"falsos positivos: {sorted(set(marcados) - set(inyectadas))}")
    print(f"escrito: {salida}")


if __name__ == "__main__":
    main()
