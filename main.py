# main.py
# La API que expone el grafo LangGraph al mundo exterior

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone

from agents import grafo  # Importamos el grafo que construimos en agents.py

# ─── MODELOS DE DATOS ─────────────────────────────────────────────
# Pydantic valida automáticamente que los datos que llegan tengan
# el formato correcto. Si algo falta o tiene tipo incorrecto, devuelve
# un error 422 claro en vez de crashear

class ReporteEntrada(BaseModel):
    barrio:    str
    condicion: str   # 'soleado', 'nublado', 'lloviendo', 'tormenta', 'neblina'

class ConsultaEntrada(BaseModel):
    barrio_consulta:     str
    reportes_ciudadanos: List[ReporteEntrada] = Field(default_factory=list)
    # default_factory=list significa que si no envían reportes, la lista
    # empieza vacía — no da error

class ResultadoSalida(BaseModel):
    barrio:              str
    condicion_predicha:  Optional[str]
    probabilidad_lluvia: Optional[float]
    nivel_alerta:        Optional[str]
    mensaje_final:       Optional[str]
    contradiccion:       Optional[bool]
    errores:             List[str]


# ─── APLICACIÓN ───────────────────────────────────────────────────
app = FastAPI(
    title="ClimaMZ API",
    description="Predicción climática multiagente para Manizales, Colombia",
    version="1.0.0"
)

# CORS: permite que el frontend (en otro dominio) llame a esta API
# Sin esto, el navegador bloquea las peticiones por seguridad
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # En producción real deberías poner la URL exacta del frontend
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── ENDPOINTS ────────────────────────────────────────────────────

@app.get("/")
def raiz():
    """Endpoint de verificación — confirma que la API está viva."""
    return {"estado": "activo", "sistema": "ClimaMZ API v1.0"}


@app.get("/health")
def health():
    """Render usa este endpoint para saber si el servicio está sano."""
    return {"status": "ok"}


@app.post("/predecir", response_model=ResultadoSalida)
async def predecir(consulta: ConsultaEntrada):
    """
    Endpoint principal.
    Recibe el barrio y los reportes ciudadanos,
    ejecuta el grafo LangGraph y devuelve la predicción.
    """

    # Convertimos los reportes al formato que espera el grafo
    ahora = datetime.now(timezone.utc).isoformat()
    reportes_formateados = [
        {
            "barrio":    r.barrio.lower().strip(),
            "condicion": r.condicion.lower().strip(),
            "timestamp": ahora,   # Usamos la hora actual del servidor
            "peso":      0.5      # Peso inicial — el validador lo recalcula
        }
        for r in consulta.reportes_ciudadanos
    ]

    estado_inicial = {
        "barrio_consulta":     consulta.barrio_consulta,
        "reportes_ciudadanos": reportes_formateados,
        "datos_api":           None,
        "errores":             []
    }

    try:
        resultado = await grafo.ainvoke(estado_inicial)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del grafo: {str(e)}"
        )

    return ResultadoSalida(
        barrio=consulta.barrio_consulta,
        condicion_predicha=resultado.get("condicion_predicha"),
        probabilidad_lluvia=resultado.get("probabilidad_lluvia"),
        nivel_alerta=resultado.get("nivel_alerta"),
        mensaje_final=resultado.get("mensaje_final"),
        contradiccion=resultado.get("contradiccion_detectada"),
        errores=resultado.get("errores", [])
    )
