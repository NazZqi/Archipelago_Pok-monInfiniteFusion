#!/usr/bin/env python3
"""
=============================================================================
  Archipelago Multiworld Client para Pokémon Infinite Fusion
=============================================================================
  Este script tiene dos tareas simultáneas:
  1. Conectarse a un servidor de Archipelago mediante WebSockets (asyncio).
  2. Levantar un servidor HTTP local para comunicarse con el juego.
=============================================================================
"""

import json
import threading
import time
import sys
import asyncio
import websockets
import queue
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# ─── Configuración Local (Juego) ─────────────────────────────────────────────
HTTP_HOST = "127.0.0.1"
HTTP_PORT = 5050

# ─── Configuración Archipelago ───────────────────────────────────────────────
AP_SERVER = "ws://localhost:38281"
AP_SLOT_NAME = "nazqi1"
AP_PASSWORD = ""

# ─── Colores ─────────────────────────────────────────────────────────────────
class Color:
    RESET   = "\033[0m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    CYAN    = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

def timestamp(): return datetime.now().strftime("%H:%M:%S")
def log_ap(msg): print(f"{Color.DIM}[{timestamp()}]{Color.RESET} {Color.MAGENTA}[Archipelago]{Color.RESET} {msg}")
def log_http(msg): print(f"{Color.DIM}[{timestamp()}]{Color.RESET} {Color.CYAN}[HTTP Bridge]{Color.RESET} {msg}")

# ─── Estado y Colas ──────────────────────────────────────────────────────────
# Cola de mensajes desde el HTTP al WebSocket
ap_send_queue = queue.Queue()
# Cola de ítems recibidos desde Archipelago hacia el juego
game_receive_queue = queue.Queue()

game_connected = False
last_seen = 0.0

# ─── Cargar Mapeo de Ubicaciones ─────────────────────────────────────────────
try:
    with open("client_mapping.json", "r", encoding="utf-8") as f:
        LOCATION_MAPPING = json.load(f)
    log_ap(f"Mapeo cargado: {len(LOCATION_MAPPING)} ubicaciones.")
except FileNotFoundError:
    print(f"{Color.RED}Error: client_mapping.json no encontrado.{Color.RESET}")
    print("Ejecuta primero el apworld_generator.py para extraer las ubicaciones.")
    sys.exit(1)

# ─── Cargar Diccionario Inverso de Ítems ─────────────────────────────────────
try:
    with open("client_items.json", "r", encoding="utf-8") as f:
        ITEM_DICTIONARY = json.load(f)
    log_ap(f"Diccionario de ítems cargado: {len(ITEM_DICTIONARY)} ítems.")
except FileNotFoundError:
    print(f"{Color.YELLOW}Advertencia: client_items.json no encontrado. Ítems recibidos no se traducirán.{Color.RESET}")
    ITEM_DICTIONARY = {}

# ─── HTTP Server Handler ─────────────────────────────────────────────────────
class APRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass
    
    def _send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    
    def do_GET(self):
        global last_seen, game_connected
        if self.path == "/poll":
            last_seen = time.time()
            if not game_connected:
                game_connected = True
                log_http(f"{Color.BOLD}🎮 Juego Conectado{Color.RESET}")
                
            events_to_send = []
            while not game_receive_queue.empty():
                events_to_send.append(game_receive_queue.get())
            
            self._send_json_response(200, {"status": "ok", "events": events_to_send})
        else:
            self._send_json_response(404, {"error": "not_found"})
    
    def do_POST(self):
        if self.path == "/event":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body.decode("utf-8"))
                msg_type = data.get("type", "")
                
                if msg_type == "item_found":
                    map_id = str(data.get("map_id", ""))
                    event_id = str(data.get("event_id", ""))
                    key = f"{map_id}_{event_id}"
                    
                    if key in LOCATION_MAPPING:
                        ap_id = LOCATION_MAPPING[key]
                        log_http(f"📦 Recogido ítem en mapa {map_id} evento {event_id}. AP ID: {ap_id}")
                        ap_send_queue.put({"cmd": "LocationChecks", "locations": [ap_id]})
                    else:
                        log_http(f"⚠️ Ubicación {key} no encontrada en Archipelago.")
                
                self._send_json_response(200, {"status": "ok"})
            except Exception as e:
                self._send_json_response(500, {"error": str(e)})
        else:
            self._send_json_response(404, {"error": "not_found"})

# ─── Hilo del Servidor HTTP ──────────────────────────────────────────────────
def http_server_thread():
    server = HTTPServer((HTTP_HOST, HTTP_PORT), APRequestHandler)
    log_http(f"Escuchando en http://{HTTP_HOST}:{HTTP_PORT}")
    server.serve_forever()

# ─── Archipelago WebSocket Loop ──────────────────────────────────────────────
async def ap_loop():
    log_ap(f"Conectando a {AP_SERVER}...")
    try:
        async with websockets.connect(AP_SERVER) as ws:
            log_ap("Conexión WS establecida.")
            
            # 1. Enviar paquete Connect
            connect_pkt = [{
                "cmd": "Connect",
                "password": AP_PASSWORD,
                "game": "Pokemon Infinite Fusion",
                "name": AP_SLOT_NAME,
                "uuid": "pokemon_if_client_001",
                "version": {"major": 0, "minor": 6, "build": 7, "class": "Version"},
                "items_handling": 7,
                "tags": []
            }]
            await ws.send(json.dumps(connect_pkt))
            
            # Tarea para leer la cola local y enviar a AP
            async def sender():
                while True:
                    if not ap_send_queue.empty():
                        pkt = ap_send_queue.get()
                        log_ap(f"Enviando a AP: {pkt}")
                        await ws.send(json.dumps([pkt]))
                    await asyncio.sleep(0.1)
                    
            asyncio.create_task(sender())
            
            # Bucle de recepción de AP
            async for message in ws:
                packets = json.loads(message)
                for pkt in packets:
                    cmd = pkt.get("cmd")
                    if cmd == "Connected":
                        log_ap(f"{Color.GREEN}¡Autenticado en Archipelago como {AP_SLOT_NAME}!{Color.RESET}")
                        # Enviar todos los ítems recibidos pendientes
                        # NOTA: En un cliente robusto, se debe llevar registro de qué index se recibió.
                    
                    elif cmd == "ReceivedItems":
                        index = pkt.get("index", 0)
                        items = pkt.get("items", [])
                        for item_data in items:
                            item_id = item_data.get("item")
                            item_key = str(item_id)
                            
                            if item_key in ITEM_DICTIONARY:
                                entry = ITEM_DICTIONARY[item_key]
                                item_name = entry["name"]
                                item_type = entry.get("type", "item")
                                
                                if item_type == "badge":
                                    badge_id = entry.get("badge_id", 0)
                                    log_ap(f"🎁 Recibido: {Color.BOLD}{item_name}{Color.RESET} (Medalla). Enviando al juego...")
                                    game_receive_queue.put({
                                        "action": "give_badge",
                                        "badge_id": badge_id,
                                        "name": item_name
                                    })
                                else:
                                    game_id = entry.get("game_id", item_name.upper())
                                    log_ap(f"🎁 Recibido: {Color.BOLD}{item_name}{Color.RESET}. Enviando al juego...")
                                    game_receive_queue.put({
                                        "action": "give_item",
                                        "item": game_id,
                                        "quantity": 1,
                                        "name": item_name
                                    })
                            else:
                                log_ap(f"⚠️ Ítem AP desconocido (ID: {item_id}). Sin mapeo en client_items.json.")
                            
                    elif cmd == "PrintJSON":
                        # Mensajes del chat/servidor
                        text = "".join([p.get("text", "") for p in pkt.get("data", [])])
                        log_ap(f"[Chat] {text}")
                        # Enviar al juego como notificación
                        if text.strip():
                            game_receive_queue.put({
                                "action": "chat_message",
                                "text": text.strip()
                            })
                        
    except Exception as e:
        log_ap(f"{Color.RED}Error de conexión AP: {e}{Color.RESET}")

def main():
    print(f"{Color.BOLD}{Color.GREEN}================================================={Color.RESET}")
    print(f"{Color.BOLD}{Color.GREEN}   Archipelago Multiworld Client - Pokémon IF    {Color.RESET}")
    print(f"{Color.BOLD}{Color.GREEN}================================================={Color.RESET}")
    
    threading.Thread(target=http_server_thread, daemon=True).start()
    
    try:
        asyncio.run(ap_loop())
    except KeyboardInterrupt:
        print("\nCerrando cliente...")

if __name__ == "__main__":
    main()
