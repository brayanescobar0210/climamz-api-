import os
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# Importamos el grafo construido en agents.py
from agents import grafo  

# ─── MODELOS DE DATOS ─────────────────────────────────────────────

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


# ─── 💾 BASE DE DATOS TEMPORAL EN MEMORIA ──────────────────────────
# Aquí se acumularán las notificaciones que envíen los usuarios.
# Iniciamos con unos reportes de prueba para Manizales.
DB_REPORTES = [
    {"barrio": "chipre", "condicion": "soleado", "timestamp": datetime.now(timezone.utc).isoformat(), "peso": 0.5},
    {"barrio": "palermo", "condicion": "nublado", "timestamp": datetime.now(timezone.utc).isoformat(), "peso": 0.5},
    {"barrio": "milan", "condicion": "lloviendo", "timestamp": datetime.now(timezone.utc).isoformat(), "peso": 0.5}
]


# ─── APLICACIÓN ───────────────────────────────────────────────────
app = FastAPI(
    title="ClimaMZ Red Ciudadana",
    description="Predicción climática con reportes ciudadanos en tiempo real para Manizales",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── ENDPOINTS ────────────────────────────────────────────────────

# 1. INTERFAZ VISUAL AVANZADA (Dashboard + Chat)
@app.get("/", response_class=HTMLResponse)
def read_root():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ClimaMZ - Red de Monitoreo Ciudadano</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-900 text-white font-sans h-screen flex flex-col">

        <header class="bg-gray-800 p-4 text-center border-b border-gray-700 shadow-lg">
            <h1 class="text-2xl font-bold text-emerald-400">🌤️ ClimaMZ: Inteligencia Climática Comunitaria</h1>
            <p class="text-xs text-gray-400 mt-1">Multiagentes de LangGraph validando reportes en tiempo real para Manizales</p>
        </header>

        <div class="flex-1 flex flex-col md:flex-row overflow-hidden max-w-7xl w-full mx-auto p-4 gap-4">
            
            <section class="w-full md:w-1/3 bg-gray-800 p-5 rounded-xl border border-gray-700 flex flex-col gap-4 shadow-xl">
                <h2 class="text-lg font-bold text-emerald-300 flex items-center gap-2">📢 ¡Reporta el Clima de tu Barrio!</h2>
                <p class="text-xs text-gray-400">Tu reporte alimentará la base de datos que analizan los agentes inteligentes en tiempo real.</p>
                
                <hr class="border-gray-700">

                <div>
                    <label class="block text-xs font-semibold uppercase text-gray-400 mb-1">¿En qué barrio estás?</label>
                    <input type="text" id="report-barrio" placeholder="Ej. Chipre, Palermo, Alta Suiza..." 
                           class="w-full bg-gray-700 text-white p-2.5 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm">
                </div>

                <div>
                    <label class="block text-xs font-semibold uppercase text-gray-400 mb-1">¿Cómo está el cielo?</label>
                    <select id="report-condicion" class="w-full bg-gray-700 text-white p-2.5 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm">
                        <option value="soleado">☀️ Soleado / Despejado</option>
                        <option value="nublado">☁️ Nublado</option>
                        <option value="lloviendo">🌧️ Lloviendo</option>
                        <option value="tormenta">⛈️ Tormenta Eléctrica</option>
                        <option value="neblina">🌫️ Neblina Alta</option>
                    </select>
                </div>

                <button id="report-btn" class="w-full bg-emerald-600 hover:bg-emerald-500 text-white p-3 rounded-lg font-bold text-sm transition-all shadow-md mt-2">
                    Enviar Reporte a la Red
                </button>
                
                <div id="report-status" class="text-xs text-center font-semibold mt-1 hidden"></div>
            </section>

            <section class="flex-1 bg-gray-850 border border-gray-750 rounded-xl flex flex-col overflow-hidden bg-gray-800/50 shadow-xl">
                <div class="bg-gray-800 p-3 border-b border-gray-700 text-sm font-semibold text-gray-300 flex items-center gap-2">
                    💬 Consulta con el Agente Predictor
                </div>

                <main id="chat-container" class="flex-1 overflow-y-auto p-4 space-y-4">
                    <div class="flex items-start gap-2.5">
                        <div class="bg-gray-800 p-3 rounded-lg rounded-tl-none border border-gray-700 max-w-[85%] text-sm">
                            ¡Hola! Escribe el nombre de un barrio de Manizales. Analizaré los reportes ciudadanos recientes y la información meteorológica para darte un dictamen exacto.
                        </div>
                    </div>
                </main>

                <footer class="bg-gray-800 p-3 border-t border-gray-700 flex gap-2">
                    <input type="text" id="user-input" placeholder="Pregunta por un barrio (ej. Palermo)..." 
                           class="flex-1 bg-gray-700 text-white p-3 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm">
                    <button id="send-btn" class="bg-emerald-600 hover:bg-emerald-500 text-white px-5 py-3 rounded-lg font-semibold text-sm transition-all shadow-md">
                        Consultar
                    </button>
                </footer>
            </section>

        </div>

        <script>
            const chatContainer = document.getElementById('chat-container');
            const userInput = document.getElementById('user-input');
            const sendBtn = document.getElementById('send-btn');
            
            const reportBarrio = document.getElementById('report-barrio');
            const reportCondicion = document.getElementById('report-condicion');
            const reportBtn = document.getElementById('report-btn');
            const reportStatus = document.getElementById('report-status');

            // --- 📢 FUNCIÓN PARA ENVIAR NOTIFICACIONES CIUDADANAS ---
            reportBtn.addEventListener('click', async () => {
                const barrio = reportBarrio.value.trim();
                if(!barrio) { alert("Por favor escribe el nombre del barrio"); return; }
                
                reportStatus.className = "text-xs text-center text-yellow-400 mt-1";
                reportStatus.innerText = "Subiendo reporte...";
                reportStatus.classList.remove('hidden');

                try {
                    const response = await fetch('/reportar', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ barrio: barrio, condicion: reportCondicion.value })
                    });
                    const data = await response.json();
                    
                    reportStatus.className = "text-xs text-center text-emerald-400 mt-1";
                    reportStatus.innerText = "¡Gracias! Tu reporte fue integrado con éxito.";
                    reportBarrio.value = "";
                } catch (e) {
                    reportStatus.className = "text-xs text-center text-red-400 mt-1";
                    reportStatus.innerText = "Error al enviar el reporte.";
                }
            });

            // --- 💬 FUNCIÓN PARA CHATEAR CON EL GRAFO ---
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

                appendMessage("Los agentes están analizando las notificaciones de la red...");
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
                    thinkingBubble.querySelector('div').innerText = "Error al procesar la predicción multiagente.";
                }
            }

            sendBtn.addEventListener('click', sendMessage);
            userInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
        </script>
    </body>
    </html>
    """


# 2. NUEVO ENDPOINT: RECIBIR Y ACUMULAR REPORTES DE USUARIOS
@app.post("/reportar")
def reportar_clima(reporte: ReporteEntrada):
    """Guarda en la base de datos global el clima reportado por el vecino."""
    ahora = datetime.now(timezone.utc).isoformat()
    
    # Añadimos el nuevo reporte al inicio de nuestra base de datos en memoria
    DB_REPORTES.insert(0, {
        "barrio":    reporte.barrio.lower().strip(),
        "condicion": reporte.condicion.lower().strip(),
        "timestamp": ahora,
        "peso":      0.8  # Le damos buen peso inicial por ser reportado en vivo
    })
    return {"status": "success", "mensaje": "Reporte registrado en la red de Manizales"}


# 3. ENDPOINT DEL CHAT: CONECTADO A LA BASE DE DATOS REAL
@app.post("/chat")
async def chat(input_data: Query):
    """
    Toma la pregunta, le inyecta TODOS los reportes acumulados de la ciudadanía,
    y ejecuta LangGraph para resolver de forma exacta.
    """
    # IMPORTANTE: Ahora 'reportes_ciudadanos' lleva la DB_REPORTES real acumulada.
    estado_inicial = {
        "barrio_consulta":     input_data.message.strip().lower(),
        "reportes_ciudadanos": DB_REPORTES, 
        "datos_api":           None,
        "errores":             []
    }

    try:
        resultado = await grafo.ainvoke(estado_inicial)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en LangGraph: {str(e)}")
    
    respuesta_texto = resultado.get("mensaje_final")
    
    if not respuesta_texto:
        condicion = resultado.get("condicion_predicha", "No determinada")
        alerta = resultado.get("nivel_alerta", "Inexistente")
        respuesta_texto = f"Análisis para '{input_data.message}':\\n• Estado: {condicion}\\n• Alerta: {alerta}"

    return {"respuesta": respuesta_texto}


# 4. ENDPOINT PARA DESPLIEGUES (STRICT)
@app.post("/predecir", response_model=ResultadoSalida)
async def predecir(consulta: ConsultaEntrada):
    """Endpoint clásico por si se requiere inyectar datos puros via JSON externo."""
    estado_inicial = {
        "barrio_consulta":     consulta.barrio_consulta.lower().strip(),
        "reportes_ciudadanos": [
            {
                "barrio": r.barrio.lower().strip(),
                "condicion": r.condicion.lower().strip(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "peso": 0.5
            } for r in consulta.reportes_ciudadanos
        ],
        "datos_api":           None,
        "errores":             []
    }
    resultado = await grafo.ainvoke(estado_inicial)
    return ResultadoSalida(
        barrio=consulta.barrio_consulta,
        condicion_predicha=resultado.get("condicion_predicha"),
        probabilidad_lluvia=resultado.get("probabilidad_lluvia"),
        nivel_alerta=resultado.get("nivel_alerta"),
        mensaje_final=resultado.get("mensaje_final"),
        contradiccion=resultado.get("contradiccion_detectada"),
        errores=resultado.get("errores", [])
    )

@app.get("/health")
def health():
    return {"status": "ok"}
