# Asistente inteligente para una mesa de servicios de TI

Prototipo funcional del proyecto de grado **"Diseño e implementación de un asistente inteligente para la gestión y automatización de solicitudes recurrentes en una mesa de servicios de TI"** (UNAD · Ingeniería de Sistemas · Proyecto de grado 202016907).

El asistente recibe una consulta en lenguaje natural, recupera la guía aprobada que mejor corresponde, orienta al usuario paso a paso y **escala a un analista** cuando no puede resolver el caso de forma segura. Opcionalmente usa Claude para *redactar* la respuesta, siempre apoyado en el artículo aprobado (nunca inventa contenido).

## Cómo funciona

```
Usuario → consulta → [validar y sanear] → [¿tema restringido?] ──sí──→ ESCALAR
                                              │no
                                  [recuperación TF-IDF sobre la base de conocimiento]
                                              │
                         confianza baja o consulta ambigua ──→ ESCALAR (con resumen para el analista)
                                              │suficiente
                        [redacción: Claude con el artículo, o plantilla sin IA]
                                              │
                          respuesta + fuente + "¿te sirvió?" ── no ──→ ESCALAR
                                              │
                              registro de la interacción (SQLite)
```

| Archivo | Rol |
|---|---|
| `app.py` | Interfaz Streamlit: chat, escalamientos, administración de artículos y métricas |
| `motor.py` | Normalización, TF-IDF (palabras + n-gramas de caracteres), confianza, temas restringidos, entidades |
| `ia.py` | Redacción con Claude (opcional) y respaldo sin IA; resumen para el analista |
| `db.py` | SQLite: artículos con versiones, interacciones, escalamientos, métricas, anonimización |
| `evaluar.py` | Mide el motor contra archivos de casos y guarda evidencias en `docs/` |
| `data/articulos.csv` | Base de conocimiento inicial (24 artículos, datos ficticios) |
| `tests/` | Casos de prueba y de validación |

## Requerimientos del documento maestro cubiertos

| Requerimiento | Dónde |
|---|---|
| RF-01 consulta en lenguaje natural | Chat (`app.py`) |
| RF-02 intención y entidades | `motor.py` (categoría del artículo + entidades de aplicación, sistema y dispositivo) |
| RF-03 / RF-04 consultar y presentar artículos vigentes | `motor.py`, `ia.py` (solo artículos con estado `vigente`) |
| RF-05 / RF-10 confirmación y retroalimentación | Botones 👍 / 👎 |
| RF-06 escalamiento | Confianza baja, ambigüedad, tema restringido o "No me sirvió" → pestaña *Escalamientos* |
| RF-07 trazabilidad | Tabla `interacciones` (consulta, artículo, confianza, respuesta, resultado, escalamiento) |
| RF-08 administrar artículos | Pestaña *Base de conocimiento*: edición, versión automática, historial, estado |
| RF-09 métricas | Pestaña *Métricas*, con descarga en CSV |
| RNF-01 seguridad | Pestaña de analista con clave, secretos fuera del código |
| RNF-02 / RNF-07 privacidad | Enmascarado de correos, teléfonos e IP antes de guardar |
| RNF-04 rendimiento < 5 s | Se mide y se muestra por interacción |
| RNF-05 contingencia | Si falla la API de IA, responde con la plantilla del artículo |
| RNF-08 calidad del conocimiento | Cada artículo tiene responsable, versión, fecha de revisión y estado |

## Ejecutarlo en tu computador

Requiere Python 3.10 o superior.

```bash
git clone https://github.com/Shulleiter/nivel_cero.git
cd asistente-mesa-ti
python -m venv .venv
source .venv/bin/activate          # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Se abre en `http://localhost:8501`. Sin configurar nada funciona en **modo sin IA generativa**.

### Activar la IA (opcional)

1. Crea una clave en [console.anthropic.com](https://console.anthropic.com) (la API tiene saldo propio, distinto al del chat de Claude).
2. Copia `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml` y escribe tu clave y una clave de administración propia.
3. Reinicia la app. En la barra lateral aparece el interruptor *Usar IA generativa*.

El modelo por defecto es `claude-haiku-5-5` (rápido y económico). Puedes cambiarlo con la variable de entorno `MODELO_IA`.

> **Nunca subas `secrets.toml` a GitHub.** Ya está en `.gitignore`.

## Publicarlo (Streamlit Community Cloud, gratis)

1. Sube el proyecto a un repositorio de GitHub.
2. Entra a [share.streamlit.io](https://share.streamlit.io), inicia sesión con GitHub y elige *Create app*.
3. Selecciona el repositorio, la rama `main` y el archivo `app.py`.
4. En *Advanced settings → Secrets* pega el contenido de tu `secrets.toml`.
5. Despliega. El enlace público es el que van a mostrar en el documento y en el video.

Para dar acceso de lectura al tutor: en GitHub, *Settings → Collaborators* (repositorio privado) o deja el repositorio público.

**Limitación a tener presente:** en Streamlit Community Cloud el disco no es permanente. Si la app se reinicia, SQLite vuelve a los datos iniciales. Es suficiente para la demostración; para conservar el historial de forma real habría que usar una base externa (por ejemplo Supabase o PostgreSQL).

## Evaluación

```bash
python evaluar.py                          # casos de ajuste
python evaluar.py tests/casos_validacion.csv
python evaluar.py tests/casos_nuevos.csv
```

Cada corrida genera `docs/resultados_<archivo>.csv` con el detalle caso por caso, útil como evidencia en el documento.

| Conjunto | Casos | Decisión correcta | Respuestas erróneas | Cómo se usó |
|---|---|---|---|---|
| `casos_prueba.csv` | 64 | 100 % | 0 % | **Se usó para ajustar** el motor y los sinónimos: la cifra está inflada |
| `casos_validacion.csv` | 28 | 96,4 % | 0 % | Primera corrida: 82,1 %. Después se ampliaron sinónimos y se bajó el umbral a partir de sus fallos, así que **ya no es independiente** |
| `casos_nuevos.csv` | 17 | 82,4 % | 11,8 % (2 casos) | Frases nuevas, **sin ajustar**: es la cifra más cercana a lo que verá un usuario real |

Tiempo de procesamiento del motor: unos 2 ms por consulta (la IA, si se usa, añade la latencia de la API).

**Cómo leer estos números:** con 24 artículos y casos escritos por el mismo equipo, el resultado de un conjunto ajustado no demuestra nada. Para el informe de validación conviene que cada integrante escriba 10 o 15 consultas nuevas **antes** de mirar la base de conocimiento, y que se reporte esa cifra. Los errores se concentran en frases con pocas palabras en común con los artículos (por ejemplo, *"la computadora está muy lenta"* contra un artículo que dice *"computador"*). Se mejoran ampliando `palabras_clave` y `sintomas` de los artículos, lo que se puede hacer desde la pestaña de administración.

## Qué NO está validado todavía

- **La redacción con IA real no se probó** con una clave válida durante el desarrollo; sí se probó que, con una clave inválida, el sistema se recupera y responde con la plantilla. Hagan una prueba con su clave antes de grabar el video.
- La clasificación usa TF-IDF (coincidencia de palabras), **no entiende el significado**. Una consulta con palabras muy distintas a las de los artículos puede escalarse sin necesidad, o muy rara vez confundirse con otro artículo.
- Los 24 artículos son ficticios y genéricos. Para el piloto deben reemplazarse o ajustarse a la mesa de servicios real y con datos anonimizados.
- La interfaz se probó con pruebas automáticas (`streamlit.testing`) y arrancando el servidor, pero **no se revisó visualmente en un navegador**.

## Seguridad y privacidad

- Las claves van en `secrets.toml` o variables de entorno, nunca en el código.
- Cambia la clave de administración por defecto (`admin123`) antes de publicar.
- Las consultas se guardan con correos, teléfonos e IP enmascarados. No escribas datos personales reales en las pruebas.
- Temas como contraseñas ajenas, desactivar el antivirus, malware o modificar bases de datos críticas **siempre se escalan**; la lista está en `motor.py` (`TEMAS_RESTRINGIDOS`).
- Con IA activa, el modelo solo recibe el artículo recuperado y la consulta, y tiene instrucciones de ignorar órdenes que vengan dentro de la consulta.
