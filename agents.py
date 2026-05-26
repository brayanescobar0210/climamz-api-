# agents.py
# Todo el código del grafo LangGraph en un solo archivo importable

import os
import httpx
import operator
from datetime import datetime, timezone
from typing import TypedDict, Optional, List, Annotated

from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

# ─── CONFIGURACIÓN ────────────────────────────────────────────────
# En Render, la API key viene de variables de entorno (no de Secrets de Colab)
# os.environ.get busca la variable en el sistema operativo
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY")
MANIZALES_LAT    = 5.0703
MANIZALES_LON    = -75.5138

BARRIOS_MANIZALES = [
    "chipre", "el cable", "la enea", "campus", "palermo",
    "belén", "la sultana", "san jorge", "palogrande",
    "versalles", "la estrella", "san cayetano", "villahermosa",
    "aranjuez", "bosques del norte", "milán", "la fuente",
    "alto tablazo", "san antonio", "fátima", "granada",
    "las américas", "los cedros", "el bosque", "santa helena"
]

CONDICIONES_VALIDAS = ["soleado", "nublado", "lloviendo", "tormenta", "neblina"]

WEATHERCODE_A_CONDICION = {
    0:  "soleado",   1:  "soleado",   2:  "nublado",
    3:  "nublado",   45: "neblina",   48: "neblina",
    51: "lloviendo", 53: "lloviendo", 55: "lloviendo",
    61: "lloviendo", 63: "lloviendo", 65: "lloviendo",
    80: "lloviendo", 81: "lloviendo", 82: "lloviendo",
    95: "tormenta",  96: "tormenta",  99: "tormenta",
}

# ─── LLM ──────────────────────────────────────────────────────────
# Se inicializa una sola vez cuando el servidor arranca
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=GROQ_API_KEY,
    temperature=0.2,
    max_tokens=300
)

# ─── AGENTES ──────────────────────────────────────────────────────

async def agente_recolector(state: dict) -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={MANIZALES_LAT}&longitude={MANIZALES_LON}"
        f"&current=temperature_2m,precipitation,weathercode,"
        f"relativehumidity_2m,windspeed_10m"
        f"&timezone=America%2FBogota&forecast_days=1"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            datos = r.json()
        return {
            "datos_api": {
                "temperatura":      datos["current"]["temperature_2m"],
                "precipitacion_mm": datos["current"]["precipitation"],
                "weathercode":      datos["current"]["weathercode"],
                "humedad":          datos["current"]["relativehumidity_2m"],
                "viento_kmh":       datos["current"]["windspeed_10m"],
                "fuente":           "open-meteo",
            },
            "paso_actual": "recoleccion_completa"
        }
    except Exception as e:
        return {
            "datos_api":   None,
            "errores":     [f"Error Open-Meteo: {str(e)}"],
            "paso_actual": "recoleccion_fallida"
        }


def agente_validador(state: dict) -> dict:
    reportes = state.get("reportes_ciudadanos", [])
    if not reportes:
        return {"reportes_ciudadanos": [], "paso_actual": "validacion_sin_reportes"}

    evaluados = []
    for r in reportes:
        peso  = 0.5
        barrio = r.get("barrio", "").lower().strip()

        if barrio in BARRIOS_MANIZALES:
            peso += 0.1
        else:
            peso -= 0.2

        if r.get("condicion") not in CONDICIONES_VALIDAS:
            peso -= 0.3

        try:
            ts    = datetime.fromisoformat(r.get("timestamp", ""))
            ahora = datetime.now(timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            minutos = (ahora - ts).total_seconds() / 60
            if minutos <= 30:
                peso += 0.2
            elif minutos <= 60:
                peso += 0.1
            elif minutos > 120:
                peso -= 0.2
        except (ValueError, TypeError):
            peso -= 0.1

        coincidentes = [
            x for x in reportes
            if x.get("barrio", "").lower().strip() == barrio
        ]
        if len(coincidentes) >= 3:
            peso += 0.15
        elif len(coincidentes) >= 2:
            peso += 0.05

        peso = round(max(0.0, min(1.0, peso)), 2)
        evaluados.append({**r, "peso": peso})

    return {"reportes_ciudadanos": evaluados, "paso_actual": "validacion_completa"}


def agente_fusionador(state: dict) -> dict:
    datos_api = state.get("datos_api")
    reportes  = state.get("reportes_ciudadanos", [])

    if datos_api:
        condicion_api = WEATHERCODE_A_CONDICION.get(
            datos_api.get("weathercode", 0), "nublado"
        )
        confianza_api = 0.65
        if datos_api.get("precipitacion_mm", 0) > 0:
            confianza_api += 0.10
    else:
        condicion_api = None
        confianza_api = 0.0

    validos = [r for r in reportes if r.get("peso", 0) >= 0.3]
    if validos:
        votos = {}
        for r in validos:
            c = r.get("condicion")
            votos[c] = votos.get(c, 0) + r.get("peso", 0.3)
        condicion_ciud = max(votos, key=votos.get)
        confianza_ciud = round(votos[condicion_ciud] / sum(votos.values()), 2)
        if len(validos) >= 5:
            confianza_ciud = min(1.0, confianza_ciud + 0.1)
    else:
        condicion_ciud = None
        confianza_ciud = 0.0

    contradiccion = False
    if condicion_api and condicion_ciud:
        if condicion_api == condicion_ciud:
            condicion_final = condicion_api
            confianza_final = min(1.0, (confianza_api + confianza_ciud) / 2 + 0.15)
        else:
            contradiccion   = True
            if confianza_ciud > confianza_api:
                condicion_final = condicion_ciud
                confianza_final = round(confianza_ciud * 0.85, 2)
            else:
                condicion_final = condicion_api
                confianza_final = round(confianza_api * 0.85, 2)
    elif condicion_api:
        condicion_final = condicion_api
        confianza_final = confianza_api
    elif condicion_ciud:
        condicion_final = condicion_ciud
        confianza_final = confianza_ciud
    else:
        condicion_final = "nublado"
        confianza_final = 0.1

    return {
        "condicion_predicha":          condicion_final,
        "nivel_confianza_api":         confianza_api,
        "nivel_confianza_ciudadanos":  confianza_ciud,
        "contradiccion_detectada":     contradiccion,
        "paso_actual":                 "fusion_completa"
    }


def agente_predictor(state: dict) -> dict:
    condicion     = state.get("condicion_predicha", "nublado")
    datos_api     = state.get("datos_api") or {}
    contradiccion = state.get("contradiccion_detectada", False)

    probs_base = {
        "soleado": 0.10, "nublado": 0.40, "lloviendo": 0.85,
        "tormenta": 0.95, "neblina": 0.30
    }
    prob = probs_base.get(condicion, 0.40)

    humedad = datos_api.get("humedad", 70)
    if humedad > 85:
        prob = min(1.0, prob + 0.10)
    elif humedad < 60:
        prob = max(0.0, prob - 0.10)

    if datos_api.get("precipitacion_mm", 0) > 5:
        prob = min(1.0, prob + 0.10)

    if contradiccion:
        prob = prob * 0.7 + 0.5 * 0.3

    prob = round(prob, 2)

    if condicion == "tormenta":
        nivel = "rojo"
    elif condicion == "lloviendo" and prob >= 0.75:
        nivel = "naranja"
    elif condicion in ["lloviendo", "nublado"] and prob >= 0.50:
        nivel = "amarillo"
    else:
        nivel = "verde"

    if contradiccion and nivel == "verde":
        nivel = "amarillo"

    return {
        "probabilidad_lluvia": prob,
        "nivel_alerta":        nivel,
        "paso_actual":         "prediccion_completa"
    }


def agente_interpretador(state: dict) -> dict:
    barrio        = state.get("barrio_consulta", "Manizales")
    condicion     = state.get("condicion_predicha", "nublado")
    prob          = state.get("probabilidad_lluvia", 0.5)
    nivel         = state.get("nivel_alerta", "verde")
    conf_api      = state.get("nivel_confianza_api", 0.0)
    conf_ciud     = state.get("nivel_confianza_ciudadanos", 0.0)
    contradiccion = state.get("contradiccion_detectada", False)
    reportes      = state.get("reportes_ciudadanos", [])
    errores       = state.get("errores", [])
    num_rep       = len([r for r in reportes if r.get("peso", 0) >= 0.3])

    contexto = f"""Eres el sistema de predicción climática de Manizales, Colombia.
Genera un mensaje claro, útil y en español para un ciudadano común.
Máximo 4 oraciones, sin tecnicismos. NO inventes datos.

DATOS:
- Barrio: {barrio}
- Condición: {condicion}
- Probabilidad lluvia: {int(prob * 100)}%
- Nivel de alerta: {nivel}
- Reportes ciudadanos válidos: {num_rep}
- Confianza API: {int(conf_api * 100)}%
- Confianza ciudadanos: {int(conf_ciud * 100)}%
- Contradicción entre fuentes: {'Sí' if contradiccion else 'No'}
- Errores: {errores if errores else 'Ninguno'}

REGLAS:
1. Rojo → advierte, recomienda no salir
2. Naranja → precaución, llevar paraguas
3. Amarillo → posibilidad de lluvia
4. Verde → mensaje tranquilizador
5. Contradicción → menciona incertidumbre
6. Si hay reportes → menciónalos
7. Termina SIEMPRE con la probabilidad en porcentaje"""

    try:
        resp    = llm.invoke([
            SystemMessage(content=contexto),
            HumanMessage(content="Genera el mensaje climático.")
        ])
        mensaje = resp.content.strip()
    except Exception as e:
        print(f"ERROR GROQ: {str(e)}")
        emojis  = {"verde": "🟢", "amarillo": "🟡", "naranja": "🟠", "rojo": "🔴"}
        mensaje = (
            f"{emojis.get(nivel,'🌤️')} En {barrio}, condición: {condicion}. "
            f"Probabilidad de lluvia: {int(prob * 100)}%. "
            f"Nivel de alerta: {nivel.upper()}."
        )
        if num_rep > 0:
            mensaje += f" ({num_rep} ciudadanos confirmaron esto.)"

    return {"mensaje_final": mensaje, "paso_actual": "interpretacion_completa"}


# ─── GRAFO ────────────────────────────────────────────────────────

def decidir_ruta(state: dict) -> str:
    validos = [r for r in state.get("reportes_ciudadanos", []) if r.get("peso", 0) >= 0.3]
    return "con_reportes" if validos else "sin_reportes"


def construir_grafo():
    builder = StateGraph(dict)
    builder.add_node("recolector",    agente_recolector)
    builder.add_node("validador",     agente_validador)
    builder.add_node("fusionador",    agente_fusionador)
    builder.add_node("predictor",     agente_predictor)
    builder.add_node("interpretador", agente_interpretador)

    builder.add_edge(START,           "recolector")
    builder.add_edge("recolector",    "validador")
    builder.add_edge("fusionador",    "predictor")
    builder.add_edge("predictor",     "interpretador")
    builder.add_edge("interpretador", END)

    builder.add_conditional_edges(
        "validador", decidir_ruta,
        {"con_reportes": "fusionador", "sin_reportes": "predictor"}
    )
    return builder.compile()


# Esta línea crea el grafo cuando el archivo se importa
# FastAPI lo usa directamente sin tener que construirlo en cada petición
grafo = construir_grafo()
