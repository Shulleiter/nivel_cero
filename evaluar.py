"""Evalúa el motor contra un archivo de casos de prueba y genera evidencias.

Uso:  python evaluar.py                       (usa tests/casos_prueba.csv)
      python evaluar.py tests/casos_validacion.csv

El CSV tiene dos columnas: consulta, esperado (id de artículo o ESCALAR).
Genera docs/resultados_<archivo>.csv con el detalle de cada caso.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from motor import MotorRecuperacion

BASE = Path(__file__).parent


def evaluar(ruta_casos: Path, imprimir: bool = True) -> dict:
    articulos = pd.read_csv(BASE / "data" / "articulos.csv", dtype=str).fillna("").to_dict("records")
    motor = MotorRecuperacion(articulos)
    casos = pd.read_csv(ruta_casos, dtype=str).fillna("")

    filas = []
    for _, c in casos.iterrows():
        r = motor.procesar(c["consulta"])
        obtenido = r.articulo["id"] if r.decision == "responder" else "ESCALAR"
        filas.append({"consulta": c["consulta"], "esperado": c["esperado"], "obtenido": obtenido,
                      "confianza": round(r.confianza, 3), "correcto": obtenido == c["esperado"],
                      "tiempo_ms": r.tiempo_ms, "motivo": r.motivo})
    df = pd.DataFrame(filas)

    en_alcance = df[df.esperado != "ESCALAR"]
    fuera = df[df.esperado == "ESCALAR"]
    resumen = {
        "casos": len(df),
        "decision_correcta_%": round(100 * df.correcto.mean(), 1),
        "precision_clasificacion_en_alcance_%": round(100 * en_alcance.correcto.mean(), 1),
        "escalamiento_correcto_fuera_de_alcance_%": round(100 * fuera.correcto.mean(), 1) if len(fuera) else None,
        "respuestas_erroneas_%": round(100 * ((df.obtenido != "ESCALAR") & ~df.correcto).mean(), 1),
        "escalamientos_innecesarios_%": round(100 * ((df.obtenido == "ESCALAR") & (df.esperado != "ESCALAR")).mean(), 1),
        "tiempo_medio_ms": round(df.tiempo_ms.mean(), 2),
        "tiempo_max_ms": round(df.tiempo_ms.max(), 2),
    }
    destino = BASE / "docs" / f"resultados_{ruta_casos.stem}.csv"
    destino.parent.mkdir(exist_ok=True)
    df.to_csv(destino, index=False, encoding="utf-8")

    if imprimir:
        print(f"\n== Evaluación: {ruta_casos.name} ==")
        for k, v in resumen.items():
            print(f"  {k:46} {v}")
        fallos = df[~df.correcto]
        if len(fallos):
            print(f"\n  Casos fallidos ({len(fallos)}):")
            for _, f in fallos.iterrows():
                print(f"   - [{f.esperado} -> {f.obtenido} | {f.confianza}] {f.consulta}")
        print(f"\n  Detalle guardado en {destino.relative_to(BASE)}")
    return resumen


if __name__ == "__main__":
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "tests" / "casos_prueba.csv"
    evaluar(ruta)
