"""Motor de clasificación y recuperación del asistente de mesa de servicios.

Flujo (alineado con el documento maestro):
  1. Se valida y normaliza la consulta (RF-01).
  2. Se detectan temas restringidos que nunca se automatizan.
  3. Se recuperan los artículos vigentes más parecidos con TF-IDF (RF-03).
  4. Se calcula un nivel de confianza; si es bajo, se escala (RF-06).
  5. Se extraen entidades básicas (aplicación, sistema, dispositivo) (RF-02).
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

MAX_LONGITUD = 500
UMBRAL_CONFIANZA = 0.16   # por debajo de este valor se escala al analista
UMBRAL_AMBIGUEDAD = 1.15  # el mejor puntaje debe superar al segundo por este factor
                          # o estar por encima de UMBRAL_SEGURO
UMBRAL_SEGURO = 0.40

STOPWORDS = {
    "a", "al", "algo", "ante", "con", "como", "cual", "cuando", "de", "del", "el", "ella",
    "en", "es", "esta", "este", "esto", "hay", "la", "las", "le", "lo", "los", "me", "mi",
    "mis", "muy", "no", "nos", "o", "para", "pero", "por", "que", "se", "si", "sin", "su",
    "sus", "te", "tengo", "un", "una", "uno", "unos", "y", "ya", "yo", "puedo", "quiero",
    "necesito", "ayuda", "favor", "hola", "buenas", "buenos", "dias", "tardes", "gracias",
    "poder", "puede", "estoy", "estan", "esta", "son", "ser", "he", "mas", "mucho", "tiene",
    "tienen", "hacer", "veces", "cada", "desde", "hasta", "sobre", "cuando", "donde",
}

# Temas que el asistente nunca automatiza: se escalan siempre (controles del diseño).
TEMAS_RESTRINGIDOS = {
    "contraseña de otra persona": [
        r"contrasena de (otro|otra|mi jefe|mi companero|un companero|un usuario|alguien)",
        r"clave de (otro|otra|mi jefe|mi companero|un companero|un usuario|alguien)",
        r"(entrar|ingresar|acceder) (a|en) la cuenta de (otro|otra|mi jefe|un companero|alguien)",
    ],
    "desactivar controles de seguridad": [
        r"(desactivar|apagar|quitar|deshabilitar|saltar|evadir) (el |la )?(antivirus|firewall|seguridad|mfa|doble factor)",
    ],
    "posible incidente de seguridad": [
        r"ransomware", r"secuestr\w+ (mis |los )?(archivos|datos|equipo)", r"hackearon", r"me hackearon",
        r"virus", r"malware", r"infectad",
    ],
    "datos o sistemas críticos": [
        r"(borrar|eliminar|modificar|cambiar) (la |una )?base de datos",
        r"servidor de produccion", r"acceso (a|al) servidor",
        r"datos personales de (otro|otra|clientes|empleados|un usuario)",
    ],
}

ENTIDADES = {
    "aplicación": ["outlook", "teams", "excel", "word", "powerpoint", "onedrive", "sharepoint",
                   "vpn", "zoom", "chrome", "edge", "authenticator", "office"],
    "sistema operativo": ["windows", "mac", "macos", "linux", "android", "ios"],
    "dispositivo": ["impresora", "monitor", "teclado", "mouse", "portatil", "computador", "celular",
                    "telefono", "iphone", "diadema", "camara", "proyector", "router"],
}


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni signos, espacios compactados."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9ñ\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def quitar_stopwords(texto_norm: str) -> str:
    return " ".join(p for p in texto_norm.split() if p not in STOPWORDS)


def sanitizar(consulta: str) -> str:
    """Limita longitud y elimina caracteres de control (control de entradas)."""
    consulta = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", consulta or "")
    return consulta.strip()[:MAX_LONGITUD]


@dataclass
class Resultado:
    consulta: str
    consulta_norm: str
    decision: str                       # "responder" | "escalar"
    motivo: str                         # por qué se tomó la decisión
    confianza: float = 0.0
    articulo: dict | None = None
    alternativas: list[dict] = field(default_factory=list)
    entidades: dict = field(default_factory=dict)
    tema_restringido: str | None = None
    tiempo_ms: float = 0.0


class MotorRecuperacion:
    def __init__(self, articulos: list[dict]):
        self.articulos = [a for a in articulos if str(a.get("estado", "")).lower() == "vigente"]
        if not self.articulos:
            raise ValueError("No hay artículos vigentes en la base de conocimiento.")
        docs = [self._texto_indexable(a) for a in self.articulos]
        # Dos vistas: palabras (significado) y n-gramas de caracteres (tolera errores de tipeo).
        self.vec_palabras = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
        self.vec_chars = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
        self.m_palabras = self.vec_palabras.fit_transform(docs)
        self.m_chars = self.vec_chars.fit_transform(docs)

    @staticmethod
    def _texto_indexable(a: dict) -> str:
        # El título y las palabras clave pesan más: se repiten.
        partes = [a.get("titulo", ""), a.get("titulo", ""), a.get("palabras_clave", ""),
                  a.get("palabras_clave", ""), a.get("sintomas", ""), a.get("categoria", "")]
        return quitar_stopwords(normalizar(" ".join(str(p) for p in partes)))

    # ------------------------------------------------------------------ utilidades
    @staticmethod
    def detectar_tema_restringido(consulta_norm: str) -> str | None:
        for tema, patrones in TEMAS_RESTRINGIDOS.items():
            if any(re.search(p, consulta_norm) for p in patrones):
                return tema
        return None

    @staticmethod
    def extraer_entidades(consulta_norm: str) -> dict:
        tokens = set(consulta_norm.split())
        return {tipo: sorted(tokens.intersection(vocab)) for tipo, vocab in ENTIDADES.items()
                if tokens.intersection(vocab)}

    def _puntajes(self, consulta_norm: str) -> np.ndarray:
        q = quitar_stopwords(consulta_norm)
        if not q:
            return np.zeros(len(self.articulos))
        s_pal = cosine_similarity(self.vec_palabras.transform([q]), self.m_palabras)[0]
        s_chr = cosine_similarity(self.vec_chars.transform([q]), self.m_chars)[0]
        return 0.6 * s_pal + 0.4 * s_chr

    # ------------------------------------------------------------------ API principal
    def procesar(self, consulta: str) -> Resultado:
        t0 = time.perf_counter()
        consulta = sanitizar(consulta)
        norm = normalizar(consulta)

        if len(norm) < 3:
            return self._cerrar(Resultado(consulta, norm, "escalar",
                                          "La consulta es demasiado corta o está vacía.", 0.0), t0)

        entidades = self.extraer_entidades(norm)
        tema = self.detectar_tema_restringido(norm)
        if tema:
            return self._cerrar(Resultado(consulta, norm, "escalar",
                                          f"Tema restringido para automatización: {tema}.", 0.0,
                                          entidades=entidades, tema_restringido=tema), t0)

        puntajes = self._puntajes(norm)
        orden = np.argsort(puntajes)[::-1]
        mejor, segundo = float(puntajes[orden[0]]), float(puntajes[orden[1]]) if len(orden) > 1 else 0.0
        alternativas = [self._resumen(self.articulos[i], float(puntajes[i])) for i in orden[:3]]

        if mejor < UMBRAL_CONFIANZA:
            res = Resultado(consulta, norm, "escalar",
                            "Confianza baja: no se encontró un artículo suficientemente parecido.",
                            mejor, alternativas=alternativas, entidades=entidades)
        elif mejor < UMBRAL_SEGURO and segundo > 0 and mejor < segundo * UMBRAL_AMBIGUEDAD:
            res = Resultado(consulta, norm, "escalar",
                            "Consulta ambigua: varios artículos tienen puntajes muy cercanos.",
                            mejor, alternativas=alternativas, entidades=entidades)
        else:
            res = Resultado(consulta, norm, "responder", "Artículo vigente encontrado con confianza suficiente.",
                            mejor, articulo=self.articulos[orden[0]], alternativas=alternativas,
                            entidades=entidades)
        return self._cerrar(res, t0)

    @staticmethod
    def _resumen(a: dict, puntaje: float) -> dict:
        return {"id": a["id"], "titulo": a["titulo"], "puntaje": round(puntaje, 3)}

    @staticmethod
    def _cerrar(res: Resultado, t0: float) -> Resultado:
        res.tiempo_ms = round((time.perf_counter() - t0) * 1000, 2)
        return res


def pasos_de(articulo: dict) -> list[str]:
    return [p.strip() for p in str(articulo.get("pasos", "")).split("|") if p.strip()]
