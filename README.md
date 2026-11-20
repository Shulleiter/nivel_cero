# Asistente Inteligente para la Gestión de Solicitudes en una Mesa de Servicios de TI

Prototipo funcional desarrollado como parte del proyecto de grado "Diseño e implementación de un asistente inteligente para la gestión y automatización de solicitudes recurrentes en una mesa de servicios de TI" del programa de Ingeniería de Sistemas de la UNAD (Curso: Proyecto de grado 202016907).

El sistema es un prototipo con nivel de maduración tecnológica TRL5, diseñado para interpretar consultas en lenguaje natural, recuperar información aprobada de una base de conocimiento, orientar al usuario paso a paso y derivar a un analista humano aquellos casos que requieran intervención especializada o que representen un riesgo de seguridad.

## Descripción General

El asistente optimiza la operación de una mesa de servicios de TI mediante la automatización de la primera línea de atención. Para lograrlo, utiliza técnicas de Procesamiento de Lenguaje Natural (NLP) para encontrar la solución más adecuada dentro de un repositorio de artículos y, opcionalmente, utiliza Inteligencia Artificial Generativa (Claude) para redactar una respuesta amigable, garantizando siempre que la información entregada provenga estrictamente del conocimiento validado por la organización.

## Flujo de Procesamiento

El sistema sigue una arquitectura lógica con múltiples puntos de control para garantizar la seguridad y la calidad de las respuestas:

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

## Arquitectura y Módulos del Sistema

El software está construido en Python bajo una arquitectura modular, garantizando el mantenimiento y la escalabilidad:

* Interfaz de Usuario (app.py): Desarrollada con Streamlit. Proporciona el chat para los usuarios finales y un panel administrativo (protegido por autenticación) para la gestión del conocimiento, atención de escalamientos y visualización de métricas.
* Motor de Clasificación y Recuperación (motor.py): Núcleo del asistente. Utiliza TF-IDF (con n-gramas de palabras y caracteres) para calcular la similitud del coseno entre la consulta y los artículos. Implementa reglas de negocio para la detección de temas restringidos y el cálculo de umbrales de confianza.
* Módulo de IA Generativa (ia.py): Capa opcional que conecta con la API de Anthropic (Claude) para redactar respuestas naturales. Cuenta con un mecanismo de contingencia (fallback) a una plantilla local en caso de fallos de red o falta de configuración.
* Capa de Persistencia (db.py): Gestión de base de datos relacional (SQLite). Almacena los artículos, el historial de versiones, las interacciones y los escalamientos. Incluye funciones de anonimización (enmascaramiento de correos, teléfonos e IPs) para proteger la privacidad.

## Cobertura de Requerimientos

El diseño del prototipo da cumplimiento a los requerimientos funcionales y no funcionales definidos en el documento maestro:

* RF-01 / RF-02: Consulta en lenguaje natural e identificación de intención y entidades (app.py, motor.py).
* RF-03 / RF-04: Consulta y presentación de artículos vigentes de la base de conocimiento (motor.py, ia.py).
* RF-05 / RF-10: Confirmación de utilidad (👍/👎) y retroalimentación del usuario (app.py).
* RF-06: Escalamiento por baja confianza, ambigüedad o temas restringidos (motor.py, app.py).
* RF-07: Trazabilidad y registro auditable de cada interacción (db.py).
* RF-08: Administración de artículos con control de versiones e historial (db.py, app.py).
* RF-09: Generación de métricas de uso y desempeño (db.py, app.py).
* RNF-01 / RNF-02: Seguridad de acceso y privacidad (anonimización de datos) (app.py, db.py).
* RNF-04 / RNF-05: Rendimiento (< 5 s) y contingencia ante fallos de IA (motor.py, ia.py).

## Validación y Resultados (Evidencia TRL5)

Para demostrar el nivel de maduración TRL5, se diseñó un módulo de evaluación automatizado (evaluar.py) que mide el desempeño del motor frente a distintos conjuntos de datos de prueba.

* Casos de ajuste (casos_prueba.csv): 64 casos. 100% de decisión correcta. Utilizado para calibración inicial.
* Casos de validación (casos_validacion.csv): 28 casos. 96.4% de decisión correcta. Validación tras ajuste de sinónimos.
* Casos nuevos sin ajustar (casos_nuevos.csv): 17 casos. 82.4% de decisión correcta. Prueba ciega con frases nuevas.

Rendimiento: El tiempo de procesamiento del motor de búsqueda es de aproximadamente 2 milisegundos por consulta, cumpliendo holgadamente con el requerimiento de respuesta menor a 5 segundos (RNF-04).

## Stack Tecnológico

* Lenguaje: Python 3.10+
* Interfaz Gráfica: Streamlit
* Procesamiento de Lenguaje Natural: Scikit-learn
* Base de Datos: SQLite
* Modelo de IA (Opcional): Anthropic API (Claude)

## Autores

* Sergio Ricardo Reyes Sandoval
* Maicol Andres Marquez Arias
* Henry Ortega Murillo

Tutor: Cesar Felipe Henao Villa
Universidad Nacional Abierta y a Distancia (UNAD) - 2026
