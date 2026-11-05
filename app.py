"""Asistente inteligente para una mesa de servicios de TI - prototipo (Streamlit)."""
from __future__ import annotations

import hmac
import os
import time

import pandas as pd
import streamlit as st

import db
import ia
from motor import MotorRecuperacion, UMBRAL_CONFIANZA

st.set_page_config(page_title="Asistente Mesa de Servicios TI", page_icon="🛠️", layout="wide")
db.init_db()


# ------------------------------------------------------------------ utilidades
def secreto(nombre: str, defecto: str | None = None) -> str | None:
    """Lee un secreto de Streamlit o de una variable de entorno (nunca del código)."""
    try:
        if nombre in st.secrets:
            return str(st.secrets[nombre])
    except Exception:
        pass
    return os.environ.get(nombre, defecto)


@st.cache_resource(show_spinner=False)
def cargar_motor(firma: str) -> MotorRecuperacion:
    return MotorRecuperacion(db.cargar_articulos())


def motor() -> MotorRecuperacion:
    return cargar_motor(db.firma_articulos())


API_KEY = secreto("ANTHROPIC_API_KEY")
ADMIN_PASSWORD = secreto("ADMIN_PASSWORD", "admin123")

ss = st.session_state
ss.setdefault("mensajes", [])
ss.setdefault("admin", False)

SALUDO = ("¡Hola! Soy el asistente de la mesa de servicios de TI. Cuéntame qué problema o solicitud tienes "
          "(por ejemplo: *no puedo entrar a mi correo*, *la VPN se cae*, *la impresora no imprime*) y te "
          "oriento con las guías aprobadas. Si no puedo resolverlo, lo paso a un analista.")


# ------------------------------------------------------------------- acciones
def responder_consulta(consulta: str, usar_ia: bool) -> None:
    t0 = time.perf_counter()
    res = motor().procesar(consulta)
    usa_ia, texto = False, None

    if res.decision == "responder":
        texto, usa_ia = ia.redactar(res.consulta, res.articulo, API_KEY if usar_ia else None)
        if texto is None:  # la IA indicó que el artículo no cubre la consulta
            res.decision = "escalar"
            res.motivo = "El artículo recuperado no cubre lo que preguntó el usuario (verificado por la IA)."

    categoria = res.articulo["categoria"] if res.articulo else None
    if res.decision == "escalar":
        resumen = ia.resumen_escalamiento(res)
        texto = ("No encontré una guía segura para tu caso, así que lo pasé a un analista de soporte. "
                 "Ya dejé un resumen para que no tengas que repetir la información.")
        if res.tema_restringido:
            texto = ("Este tipo de solicitud no puede resolverse de forma automática por seguridad. "
                     "Un analista te contactará; mientras tanto no compartas contraseñas ni códigos con nadie.")
    ms = (time.perf_counter() - t0) * 1000
    iid = db.registrar_interaccion(res.consulta, categoria, res.articulo["id"] if res.articulo else None,
                                   res.confianza, res.decision, res.motivo, texto, usa_ia, ms)
    esc_id = db.crear_escalamiento(iid, resumen) if res.decision == "escalar" else None
    if esc_id:
        texto += f"\n\n🎫 Caso **#{esc_id}** registrado."

    ss.mensajes.append({"rol": "assistant", "texto": texto, "iid": iid, "pide_feedback": res.decision == "responder",
                        "fuente": f"{res.articulo['id']} v{res.articulo['version']}" if res.articulo else None,
                        "confianza": res.confianza, "usa_ia": usa_ia, "ms": ms,
                        "alternativas": res.alternativas if res.decision == "escalar" else []})
    ss.ultima_resultado = res


def dar_feedback(idx: int, util: bool) -> None:
    msg = ss.mensajes[idx]
    msg["pide_feedback"] = False
    db.registrar_feedback(msg["iid"], util)
    if util:
        ss.mensajes.append({"rol": "assistant", "texto": "¡Me alegra haberte ayudado! Si necesitas algo más, escríbeme."})
    else:
        res = ss.get("ultima_resultado")
        resumen = ia.resumen_escalamiento(res, "El usuario indicó que la orientación NO resolvió su problema.") \
            if res else "El usuario indicó que la orientación no resolvió su problema."
        esc_id = db.crear_escalamiento(msg["iid"], resumen)
        ss.mensajes.append({"rol": "assistant", "texto": f"Lamento que no haya funcionado. Pasé tu caso a un analista "
                            f"con el resumen de lo que intentamos. 🎫 Caso **#{esc_id}** registrado."})


# ------------------------------------------------------------------ barra lateral
with st.sidebar:
    st.header("🛠️ Mesa de Servicios TI")
    st.caption("Prototipo funcional · Proyecto de grado UNAD")
    if API_KEY:
        usar_ia = st.toggle("Usar IA generativa (Claude)", value=True,
                            help="La IA solo redacta usando el artículo aprobado que recuperó el motor.")
    else:
        usar_ia = False
        st.info("Modo **sin IA generativa**: el asistente muestra las guías aprobadas. "
                "Configura ANTHROPIC_API_KEY para activar la redacción con IA.")
    st.divider()
    if not ss.admin:
        with st.form("login"):
            clave = st.text_input("Clave de administración", type="password")
            if st.form_submit_button("Ingresar como analista"):
                if hmac.compare_digest(clave, ADMIN_PASSWORD or ""):
                    ss.admin = True
                    st.rerun()
                else:
                    st.error("Clave incorrecta.")
    else:
        st.success("Sesión de analista activa")
        if st.button("Cerrar sesión"):
            ss.admin = False
            st.rerun()
    if st.button("🗑️ Nueva conversación"):
        ss.mensajes = []
        st.rerun()

# ----------------------------------------------------------------------- pestañas
nombres = ["💬 Asistente"] + (["🎫 Escalamientos", "📚 Base de conocimiento", "📊 Métricas"] if ss.admin else [])
tabs = st.tabs(nombres)

# --- Chat -------------------------------------------------------------------
with tabs[0]:
    st.subheader("Asistente de soporte técnico")
    with st.chat_message("assistant"):
        st.markdown(SALUDO)
    for i, m in enumerate(ss.mensajes):
        with st.chat_message(m["rol"]):
            st.markdown(m["texto"])
            if m["rol"] == "assistant" and m.get("fuente"):
                st.caption(f"Fuente: {m['fuente']} · confianza {m['confianza']:.2f} · "
                           f"{'redactado con IA' if m['usa_ia'] else 'guía aprobada'} · {m['ms']:.0f} ms")
            if m.get("alternativas"):
                with st.expander("Artículos más cercanos (referencia para el analista)"):
                    st.table(pd.DataFrame(m["alternativas"]))
            if m.get("pide_feedback"):
                c1, c2, _ = st.columns([1, 1, 4])
                c1.button("👍 Me sirvió", key=f"ok{i}", on_click=dar_feedback, args=(i, True))
                c2.button("👎 No me sirvió", key=f"no{i}", on_click=dar_feedback, args=(i, False))

    if consulta := st.chat_input("Describe tu problema o solicitud…", max_chars=500):
        ss.mensajes.append({"rol": "user", "texto": consulta})
        with st.spinner("Buscando en la base de conocimiento…"):
            responder_consulta(consulta, usar_ia)
        st.rerun()

# --- Administración ---------------------------------------------------------
if ss.admin:
    with tabs[1]:
        st.subheader("Casos escalados")
        solo_pend = st.checkbox("Mostrar solo pendientes", value=True)
        esc = db.listar_escalamientos(solo_pend)
        if esc.empty:
            st.info("No hay casos para mostrar.")
        else:
            st.dataframe(esc[["id", "fecha", "estado", "consulta", "motivo", "analista"]], width="stretch", hide_index=True)
            sel = st.selectbox("Ver resumen del caso", esc["id"], format_func=lambda x: f"Caso #{x}")
            st.code(esc.loc[esc["id"] == sel, "resumen"].iloc[0], language=None)
            c1, c2 = st.columns([2, 1])
            nombre = c1.text_input("Nombre del analista", value="Analista")
            if c2.button("Marcar como atendido", type="primary"):
                db.atender_escalamiento(int(sel), nombre)
                st.rerun()

    with tabs[2]:
        st.subheader("Base de conocimiento")
        arts = pd.DataFrame(db.cargar_articulos())
        st.caption("Edita las celdas y guarda. Cada cambio sube la versión y deja historial. "
                   "Para retirar un artículo cambia su estado a `obsoleto`.")
        editado = st.data_editor(
            arts[["id", "titulo", "categoria", "palabras_clave", "sintomas", "pasos", "restricciones",
                  "responsable", "version", "estado", "fecha_revision"]],
            disabled=["id", "version", "fecha_revision"], hide_index=True, width="stretch",
            column_config={"estado": st.column_config.SelectboxColumn(options=["vigente", "borrador", "obsoleto"])},
            key="editor_arts")
        if st.button("💾 Guardar cambios", type="primary"):
            cambios = 0
            for _, fila in editado.iterrows():
                antes = arts.loc[arts["id"] == fila["id"]].iloc[0]
                if any(str(antes[c]) != str(fila[c]) for c in ("titulo", "categoria", "palabras_clave", "sintomas",
                                                                 "pasos", "restricciones", "responsable", "estado")):
                    db.guardar_articulo(fila.to_dict(), usuario="admin")
                    cambios += 1
            st.success(f"{cambios} artículo(s) actualizado(s).") if cambios else st.info("No hay cambios.")
            if cambios:
                st.rerun()
        with st.expander("➕ Agregar artículo nuevo"):
            with st.form("nuevo_art", clear_on_submit=True):
                n_id = st.text_input("Id (ej. RED-004)")
                n_tit = st.text_input("Título")
                n_cat = st.text_input("Categoría")
                n_kw = st.text_area("Palabras clave (separadas por ;)")
                n_sin = st.text_area("Síntomas (cómo lo describe el usuario)")
                n_pas = st.text_area("Pasos (separados por |)")
                n_res = st.text_input("Restricciones")
                n_resp = st.text_input("Responsable", value="Analista N1")
                if st.form_submit_button("Crear artículo"):
                    try:
                        db.guardar_articulo({"id": n_id, "titulo": n_tit, "categoria": n_cat, "palabras_clave": n_kw,
                                             "sintomas": n_sin, "pasos": n_pas, "restricciones": n_res,
                                             "responsable": n_resp, "version": "1.0", "estado": "vigente"}, nuevo=True)
                        st.success("Artículo creado."); st.rerun()
                    except ValueError as e:
                        st.error(str(e))
        with st.expander("🕘 Historial de versiones"):
            art_id = st.selectbox("Artículo", arts["id"])
            h = db.historial_articulo(art_id)
            st.dataframe(h, hide_index=True, width="stretch") if not h.empty else st.caption("Sin cambios registrados aún.")

    with tabs[3]:
        st.subheader("Métricas de uso y desempeño")
        m = db.metricas()
        if m["total"] == 0:
            st.info("Aún no hay interacciones registradas.")
        else:
            c = st.columns(4)
            c[0].metric("Interacciones", m["total"])
            c[1].metric("Resolución inicial", f"{m['tasa_resolucion_inicial']}%",
                        help="Casos con orientación válida sin escalamiento / total de casos.")
            c[2].metric("Escalamiento", f"{m['tasa_escalamiento']}%")
            c[3].metric("Satisfacción", f"{m['satisfaccion']}%" if m["satisfaccion"] is not None else "—",
                        help=f"Sobre {m['con_feedback']} respuestas calificadas.")
            c = st.columns(4)
            c[0].metric("Tiempo promedio", f"{m['tiempo_promedio_ms']} ms")
            c[1].metric("Tiempo p95", f"{m['tiempo_p95_ms']} ms")
            c[2].metric("Respuestas < 5 s", f"{m['pct_menor_5s']}%", help="Objetivo RNF-04.")
            c[3].metric("Casos pendientes", m["pendientes"])
            st.markdown("**Solicitudes por categoría**")
            st.bar_chart(m["por_categoria"])
            df = db.interacciones_df()
            st.markdown("**Registro de interacciones**")
            st.dataframe(df[["id", "fecha", "consulta", "categoria", "articulo_id", "confianza", "decision",
                             "usa_ia", "tiempo_ms", "util", "escalado"]], hide_index=True, width="stretch")
            st.download_button("⬇️ Descargar registro (CSV)", df.to_csv(index=False).encode("utf-8"),
                               "interacciones.csv", "text/csv")
        st.divider()
        with st.expander("⚠️ Zona de demostración"):
            if st.button("Reiniciar datos de demostración"):
                db.reiniciar_demo()
                cargar_motor.clear()
                st.success("Datos reiniciados."); st.rerun()
