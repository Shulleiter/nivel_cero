"""Capa de datos (SQLite): artículos, interacciones, escalamientos y métricas.

Cubre RF-07 (trazabilidad), RF-08 (administrar artículos con versiones),
RF-09 (métricas) y RF-10 (retroalimentación). Los datos personales se
enmascaran antes de guardar (RNF-02, RNF-07).
"""
from __future__ import annotations

import csv
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent
DB_PATH = Path(os.environ.get("ASISTENTE_DB", BASE / "data" / "asistente.db"))
CSV_ARTICULOS = BASE / "data" / "articulos.csv"

CAMPOS_ARTICULO = ["id", "titulo", "categoria", "palabras_clave", "sintomas", "pasos",
                   "restricciones", "responsable", "version", "estado", "fecha_revision"]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS articulos (
    id TEXT PRIMARY KEY, titulo TEXT NOT NULL, categoria TEXT, palabras_clave TEXT,
    sintomas TEXT, pasos TEXT, restricciones TEXT, responsable TEXT,
    version TEXT, estado TEXT, fecha_revision TEXT
);
CREATE TABLE IF NOT EXISTS articulos_historial (
    hid INTEGER PRIMARY KEY AUTOINCREMENT, articulo_id TEXT, version TEXT, titulo TEXT,
    pasos TEXT, estado TEXT, modificado_en TEXT, modificado_por TEXT
);
CREATE TABLE IF NOT EXISTS interacciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, consulta TEXT, categoria TEXT,
    articulo_id TEXT, confianza REAL, decision TEXT, motivo TEXT, respuesta TEXT,
    usa_ia INTEGER DEFAULT 0, tiempo_ms REAL, util INTEGER, escalado INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS escalamientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, interaccion_id INTEGER, fecha TEXT,
    resumen TEXT, estado TEXT DEFAULT 'pendiente', analista TEXT, atendido_en TEXT
);
"""


@contextmanager
def conexion():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def anonimizar(texto: str) -> str:
    """Enmascara correos, teléfonos/cédulas y direcciones IP antes de guardar."""
    texto = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[correo]", texto or "")
    texto = re.sub(r"\b\d{1,3}(\.\d{1,3}){3}\b", "[ip]", texto)
    texto = re.sub(r"\b\d[\d\s.-]{6,}\d\b", "[número]", texto)
    return texto


# --------------------------------------------------------------------- inicio
def init_db() -> None:
    with conexion() as con:
        con.executescript(ESQUEMA)
        if con.execute("SELECT COUNT(*) FROM articulos").fetchone()[0] == 0:
            _sembrar(con)


def _sembrar(con: sqlite3.Connection) -> None:
    with open(CSV_ARTICULOS, encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            con.execute(f"INSERT OR REPLACE INTO articulos ({','.join(CAMPOS_ARTICULO)}) "
                        f"VALUES ({','.join('?' * len(CAMPOS_ARTICULO))})",
                        [fila[c] for c in CAMPOS_ARTICULO])


def reiniciar_demo() -> None:
    """Borra interacciones, escalamientos e historial y restaura los artículos del CSV."""
    with conexion() as con:
        con.executescript("DELETE FROM interacciones; DELETE FROM escalamientos; "
                          "DELETE FROM articulos_historial; DELETE FROM articulos;")
        _sembrar(con)


# ------------------------------------------------------------------ artículos
def cargar_articulos() -> list[dict]:
    with conexion() as con:
        return [dict(r) for r in con.execute("SELECT * FROM articulos ORDER BY id")]


def firma_articulos() -> str:
    """Cambia cuando se edita la base de conocimiento (para reconstruir el índice)."""
    with conexion() as con:
        n, v = con.execute("SELECT COUNT(*), COALESCE(MAX(hid),0) FROM articulos, "
                           "(SELECT MAX(hid) AS hid FROM articulos_historial)").fetchone()
        est = con.execute("SELECT GROUP_CONCAT(estado) FROM articulos").fetchone()[0]
    return f"{n}-{v}-{hash(est)}"


def _siguiente_version(version: str) -> str:
    try:
        mayor, menor = str(version).split(".")
        return f"{mayor}.{int(menor) + 1}"
    except ValueError:
        return "1.1"


def guardar_articulo(art: dict, usuario: str = "admin", nuevo: bool = False) -> str:
    """Crea o actualiza un artículo; si cambia, sube la versión y guarda historial."""
    art = {c: str(art.get(c, "") or "").strip() for c in CAMPOS_ARTICULO}
    if not art["id"] or not art["titulo"]:
        raise ValueError("El artículo necesita un id y un título.")
    with conexion() as con:
        actual = con.execute("SELECT * FROM articulos WHERE id=?", (art["id"],)).fetchone()
        if nuevo and actual:
            raise ValueError(f"Ya existe un artículo con id {art['id']}.")
        if actual is not None:
            cambio = any(str(actual[c]) != art[c] for c in CAMPOS_ARTICULO
                         if c not in ("version", "fecha_revision"))
            if not cambio:
                return actual["version"]
            art["version"] = _siguiente_version(actual["version"])
        else:
            art["version"] = art["version"] or "1.0"
        art["fecha_revision"] = datetime.now().strftime("%Y-%m-%d")
        con.execute(f"INSERT OR REPLACE INTO articulos ({','.join(CAMPOS_ARTICULO)}) "
                    f"VALUES ({','.join('?' * len(CAMPOS_ARTICULO))})", [art[c] for c in CAMPOS_ARTICULO])
        con.execute("INSERT INTO articulos_historial (articulo_id, version, titulo, pasos, estado, "
                    "modificado_en, modificado_por) VALUES (?,?,?,?,?,?,?)",
                    (art["id"], art["version"], art["titulo"], art["pasos"], art["estado"], ahora(), usuario))
    return art["version"]


def historial_articulo(articulo_id: str) -> pd.DataFrame:
    with conexion() as con:
        return pd.read_sql_query("SELECT version, titulo, estado, modificado_en, modificado_por "
                                 "FROM articulos_historial WHERE articulo_id=? ORDER BY hid DESC",
                                 con, params=(articulo_id,))


# --------------------------------------------------------------- interacciones
def registrar_interaccion(consulta: str, categoria: str | None, articulo_id: str | None,
                          confianza: float, decision: str, motivo: str, respuesta: str,
                          usa_ia: bool, tiempo_ms: float) -> int:
    with conexion() as con:
        cur = con.execute(
            "INSERT INTO interacciones (fecha, consulta, categoria, articulo_id, confianza, decision, "
            "motivo, respuesta, usa_ia, tiempo_ms, escalado) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ahora(), anonimizar(consulta), categoria, articulo_id, round(confianza, 3), decision, motivo,
             respuesta, int(usa_ia), round(tiempo_ms, 1), int(decision == "escalar")))
        return cur.lastrowid


def registrar_feedback(interaccion_id: int, util: bool) -> None:
    with conexion() as con:
        con.execute("UPDATE interacciones SET util=? WHERE id=?", (int(util), interaccion_id))
        if not util:
            con.execute("UPDATE interacciones SET escalado=1 WHERE id=?", (interaccion_id,))


def crear_escalamiento(interaccion_id: int, resumen: str) -> int:
    with conexion() as con:
        cur = con.execute("INSERT INTO escalamientos (interaccion_id, fecha, resumen) VALUES (?,?,?)",
                          (interaccion_id, ahora(), anonimizar(resumen)))
        return cur.lastrowid


def listar_escalamientos(solo_pendientes: bool = False) -> pd.DataFrame:
    consulta = ("SELECT e.id, e.fecha, e.estado, e.analista, e.atendido_en, e.resumen, "
                "i.consulta, i.motivo FROM escalamientos e LEFT JOIN interacciones i "
                "ON i.id = e.interaccion_id")
    if solo_pendientes:
        consulta += " WHERE e.estado='pendiente'"
    with conexion() as con:
        return pd.read_sql_query(consulta + " ORDER BY e.id DESC", con)


def atender_escalamiento(escalamiento_id: int, analista: str) -> None:
    with conexion() as con:
        con.execute("UPDATE escalamientos SET estado='atendido', analista=?, atendido_en=? WHERE id=?",
                    (analista or "analista", ahora(), escalamiento_id))


def interacciones_df() -> pd.DataFrame:
    with conexion() as con:
        return pd.read_sql_query("SELECT * FROM interacciones ORDER BY id DESC", con)


# -------------------------------------------------------------------- métricas
def metricas() -> dict:
    df = interacciones_df()
    total = len(df)
    if total == 0:
        return {"total": 0}
    resueltas = int(((df.decision == "responder") & (df.escalado == 0)).sum())
    con_feedback = df.util.notna().sum()
    return {
        "total": total,
        "tasa_resolucion_inicial": round(100 * resueltas / total, 1),
        "tasa_escalamiento": round(100 * int((df.escalado == 1).sum()) / total, 1),
        "satisfaccion": round(100 * float(df.util.dropna().mean()), 1) if con_feedback else None,
        "con_feedback": int(con_feedback),
        "tiempo_promedio_ms": round(float(df.tiempo_ms.mean()), 1),
        "tiempo_p95_ms": round(float(df.tiempo_ms.quantile(0.95)), 1),
        "pct_menor_5s": round(100 * float((df.tiempo_ms < 5000).mean()), 1),
        "pendientes": int((listar_escalamientos(True)).shape[0]),
        "por_categoria": df[df.categoria.notna()].groupby("categoria").size().sort_values(ascending=False),
    }
