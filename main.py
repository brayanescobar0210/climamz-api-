import os
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# Importamos el grafo que construiste en agents.py
from agents import grafo  

# ─── MODELOS DE DATOS (PYDANTIC) ───────────────────────────────────

class ReporteEntrada(BaseModel):
    barrio:    str
    condicion: str   # 'soleado', 'nublado', 'lloviendo', 'tormenta', 'neblina'

class ConsultaEntrada(BaseModel):
    barrio_consulta:     str
    reportes_ciudadanos: List[ReporteEntrada] = Field(default_factory=list)

class ResultadoSalida(BaseModel):
    barrio:              str
    condicion_predicha:  Optional[str] = None
    probabilidad_lluvia: Optional[float] = None
    nivel_alerta:        Optional[str] = None
    mensaje_final:       Optional[str] = None
    contradiccion:       Optional[bool] = None
    errores:             List[str]

class Query(BaseModel):
    message: str


# ─── CONFIGURACIÓN DE LA APLICACIÓN (ÚNICA INSTANCIA) ──────────────
app = FastAPI(
    title="ClimaMZ API & UI",
    description="Predicción climática multiagente para Manizales, Colombia con Interfaz Visual",
    version="1.0.0"
)

# Configuración de CORS para permitir conexiones externas si es necesario
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── ENDPOINTS DE LA API Y LA INTERFAZ ──────────────────────────────

# 1. LA INTERFAZ VISUAL (Página de inicio del servidor)
@app.get("/", response_class=HTMLResponse)
def read_root():
    """Devuelve la aplicación web del chat interactivo."""
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ClimaMZ - Asistente de Clima</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-900 text-white font-sans h-screen flex flex-col">

        <header class="bg-gray-800 p-4 text-center border-b border-gray-700 shadow-md">
            <h1 class="text-xl font-bold text-emerald-400">🌤️ ClimaMZ Agent</h1>
            <p class="text-xs text-gray-400">Asistente inteligente para Manizales</p>
        </header>

        <main id="chat-container" class="flex-1 overflow-y-auto p-4 space-y-4 max-w-3xl w-full mx-auto">
            <div class="flex items-start gap-2.5">
                <div class="bg-gray-800 p-3 rounded-lg rounded-tl-none border border-gray-700 max-w-[85%] shadow">
                    <p class="text-sm">¡Hola! Soy tu asistente climático de Manizales. Escribe el nombre de un barrio (ej: Chipre, Palermo, Milan) para consultar su reporte climático actual.</p>
                </div>
            </div>
        </main>

        <footer class="bg-gray-800 p-4 border-t border-gray-700 shadow-inner">
            <div class="max-w-3xl mx-auto flex gap-2">
                <input type="text" id="user-input" placeholder="Escribe un barrio de Manizales..." 
                       class="flex-1 bg-gray-700 text-white p-3 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 placeholder-gray-400 text-sm">
                <button id="send-btn" class="bg-emerald-600 hover:bg-emerald-500 text-white px-5 py-3 rounded-lg font-semibold text-sm transition-all shadow-md">
                    Enviar
                </button>
            </div>
        </footer>

        <script>
            const chatContainer = document.getElementById('chat-container');
            const userInput = document.getElementById('user-input');
            const sendBtn = document.getElementById('send-btn');

            function appendMessage(text, isUser = false) {
                const wrapper = document.createElement('div');
                wrapper.className = isUser ? "flex items-start justify-end gap-2.5" : "flex items-start gap-2.5";
                
                const bubble = document.createElement('div');
                bubble.className = isUser 
                    ? "bg-emerald-600 p-3 rounded-lg rounded-tr-none max-w-[85%] shadow text-sm" 
                    : "bg-gray-800 p-3 rounded-lg rounded-tl-none border border-gray-700 max-w-[85%] shadow text-sm whitespace-pre-line";
                
                bubble.innerText = text;
                wrapper.appendChild(bubble);
                chatContainer.appendChild(wrapper);
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }

            async function sendMessage() {
                const message = userInput.value.trim();
                if (!message) return;

                appendMessage(message, true);
                userInput.value = '';

                appendMessage("Consultando con los agentes climáticos...");
                const thinkingBubble = chatContainer.lastChild;

                try {
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: message })
                    });
                    
                    const data = await response.json();
                    thinkingBubble.querySelector('div').innerText = data.respuesta;
                } catch (error) {
                    thinkingBubble.querySelector('div').innerText = "Error al conectar con el servidor climático.";
                }
            }

            sendBtn.addEventListener('click', sendMessage);
            userInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
        </script>
    </body>
    </html>
    """


# 2. ENDPOINT DEL INTERFAZ DE CHAT (Consumido por la UI)
@app.post("/chat")
async def chat(input_data: Query):
    """
    Recibe el texto del chat (asumiendo que el usuario escribe el barrio),
    configura el estado adecuado para tu LangGraph y devuelve el mensaje final.
    """
    # Creamos el estado inicial estructurado que tu LangGraph requiere obligatoriamente
    estado_inicial = {
        "barrio_consulta": input_data.message.strip(),
        "reportes_ciudadanos": [], # En consulta rápida por chat no enviamos reportes iniciales
        "datos_api": None,
        "errores": []
    }

    try:
        # Invocamos el grafo usando su nombre correcto: 'grafo'
        resultado = await grafo.ainvoke(estado_inicial)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error en los agentes climáticos: {str(e)}"
        )
    
    # Extraemos el campo 'mensaje_final' generado por tu nodo final de LangGraph
    respuesta_texto = resultado.get("mensaje_final")
    
    # En caso de que no venga un mensaje formateado, generamos una respuesta de respaldo elegante
    if not respuesta_texto:
        condicion = resultado.get("condicion_predicha", "No determinada")
        alerta = resultado.get("nivel_alerta", "Inexistente")
        respuesta_texto = f"Reporte de agentes para el sector '{input_data.message}':\\n• Predicción: {condicion}\\n• Nivel de Alerta: {alerta}"

    return {"respuesta": respuesta_texto}


# 3. ENDPOINT API DETALLADO (Para integraciones con JSON estricto)
@app.post("/predecir", response_model=ResultadoSalida)
async def predecir(consulta: ConsultaEntrada):
    """Recibe barrio y lista de reportes manuales, procesando el JSON completo."""
    ahora = datetime.now(timezone.utc).isoformat()
    reportes_formateados = [
        {
            "barrio":    r.barrio.lower().strip(),
            "condicion": r.condicion.lower().strip(),
            "timestamp": ahora,
            "peso":      0.5  
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


# 4. ENDPOINT DE MONITOREO (Para Render)
@app.get("/health")
def health():
    """Render usa este endpoint para saber si el contenedor está en línea."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
