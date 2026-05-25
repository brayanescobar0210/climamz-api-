import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse  # <-- IMPORTANTE: Añade esto
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END

# --- [AQUÍ VA TU CONFIGURACIÓN Y GRAFO DE LANGGRAPH] ---
# (Deja intacto todo tu código del clima de Manizales y la compilación del grafo)

app = FastAPI(title="ClimaMZ API & UI")

class Query(BaseModel):
    message: str

# 1. EL ENDPOINT DE LA INTERFAZ VISUAL (Página de inicio)
@app.get("/", response_class=HTMLResponse)
def read_root():
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
                    <p class="text-sm">¡Hola! Soy tu asistente climático de Manizales. ¿De qué sector o vereda quieres consultar el clima hoy?</p>
                </div>
            </div>
        </main>

        <footer class="bg-gray-800 p-4 border-t border-gray-700 shadow-inner">
            <div class="max-w-3xl mx-auto flex gap-2">
                <input type="text" id="user-input" placeholder="Pregúntame sobre el clima..." 
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
                    : "bg-gray-800 p-3 rounded-lg rounded-tl-none border border-gray-700 max-w-[85%] shadow text-sm";
                
                bubble.innerText = text;
                wrapper.appendChild(bubble);
                chatContainer.appendChild(wrapper);
                chatContainer.scrollTop = chatContainer.scrollHeight; // Auto-scroll hacia abajo
            }

            async function sendMessage() {
                const message = userInput.value.trim();
                if (!message) return;

                // 1. Mostrar mensaje del usuario en pantalla
                appendMessage(message, true);
                userInput.value = '';

                // 2. Mostrar indicador de "escribiendo..."
                appendMessage("Pensando...");
                const thinkingBubble = chatContainer.lastChild;

                try {
                    // 3. Petición automática a tu propio endpoint /chat
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: message })
                    });
                    
                    const data = await response.json();
                    
                    // 4. Reemplazar el "Pensando..." con la respuesta real de LangGraph
                    // Ajusta 'data.respuesta' según el formato exacto que devuelva tu JSON
                    thinkingBubble.querySelector('div').innerText = data.respuesta || JSON.stringify(data);
                } catch (error) {
                    thinkingBubble.querySelector('div').innerText = "Error al conectar con el agente.";
                }
            }

            sendBtn.addEventListener('click', sendMessage);
            userInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
        </script>
    </body>
    </html>
    """

# 2. TU ENDPOINT DE PROCESAMIENTO (El que ya tenías)
@app.post("/chat")
async def chat(input_data: Query):
    # Aquí despiertas a tu grafo compilado (ejemplo: 'app_graph')
    inputs = {"messages": [("user", input_data.message)]}
    resultado = await app_graph.ainvoke(inputs)
    
    # Asegúrate de extraer solo el texto de la respuesta del modelo para que la interfaz se vea limpia
    return {"respuesta": resultado["messages"][-1].content}
