import asyncio
import json
import logging
import queue
import time
import os
import subprocess
import threading
import pkgutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import urlparse, parse_qs

import colorama

from NetUtils import ClientStatus  # type: ignore
from CommonClient import CommonContext, server_loop, gui_enabled, ClientCommandProcessor, logger, get_base_parser  # type: ignore

HTTP_HOST = "127.0.0.1"
HTTP_PORT = 5050

# Cola global para mensajes HTTP -> Kivy
game_receive_queue = queue.Queue()
# Cola global para mensajes Kivy -> HTTP
ap_send_queue = queue.Queue()

game_connected = False
last_seen = 0.0
# Contexto activo; lo asigna launch() y lo lee el hilo HTTP
ctx: Optional["PokemonIFContext"] = None

try:
    _mapping_data = pkgutil.get_data(__name__, "client_mapping.json")
    LOCATION_MAPPING = json.loads(_mapping_data.decode("utf-8")) if _mapping_data else {}
except Exception as e:
    LOCATION_MAPPING = {}

try:
    _items_data = pkgutil.get_data(__name__, "client_items.json")
    ITEM_DICTIONARY = json.loads(_items_data.decode("utf-8")) if _items_data else {}
except Exception as e:
    ITEM_DICTIONARY = {}

class APRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass
    
    def _send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    
    def _server_ready(self) -> bool:
        return ctx is not None and ctx.slot is not None and ctx.server is not None and not ctx.server.socket.closed

    def _read_json(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")

    def do_GET(self):
        global last_seen, game_connected
        url = urlparse(self.path)
        if url.path != "/poll":
            self._send_json_response(404, {"error": "not_found"})
            return

        last_seen = time.time()
        if not game_connected:
            game_connected = True
            logger.info("🎮 Juego Conectado al Cliente HTTP")

        query = parse_qs(url.query)
        ready = self._server_ready()
        events_to_send = []

        # 1. Mensajes de chat pendientes
        while not game_receive_queue.empty():
            events_to_send.append(game_receive_queue.get())

        # 2. Opciones de la semilla, cuando el juego aún no las tiene (p. ej. tras reiniciarlo)
        if ready and query.get("opts") == ["1"]:
            events_to_send.append({"action": "set_options", "options": ctx.slot_data})

        # 3. Ítems recibidos desde el índice que pide el juego. El índice vive en la
        #    partida guardada: si el juego se cierra sin guardar, los vuelve a pedir.
        if ready:
            try:
                start = max(0, int(query.get("index", ["0"])[0]))
            except ValueError:
                start = 0
            for index in range(start, len(ctx.items_received)):
                events_to_send.append(item_event(ctx.items_received[index].item, index))

        self._send_json_response(200, {"status": "ok", "ready": ready, "events": events_to_send})

    def do_POST(self):
        try:
            data = self._read_json()
        except Exception as e:
            self._send_json_response(400, {"error": str(e)})
            return

        if self.path == "/event":
            # Sin servidor AP no sabemos si es una ubicación: el juego la guarda y la reintenta.
            if data.get("type") in ("item_found", "item_received") and not self._server_ready():
                self._send_json_response(200, {"status": "offline"})
                return
            if data.get("type") in ("item_found", "item_received"):
                self._send_json_response(200, resolve_location(data))
                return
            self._send_json_response(200, {"status": "ok"})

        elif self.path == "/resync":
            # El juego reenvía todo lo que ya marcó (guardado en la partida). El servidor
            # ignora duplicados, así que reenviar es seguro.
            if not self._server_ready():
                self._send_json_response(200, {"status": "offline"})
                return
            locations = [loc for loc in data.get("locations", []) if loc in ctx.server_locations]
            if locations:
                ctx.locally_sent_locations.update(locations)
                ap_send_queue.put({"cmd": "LocationChecks", "locations": locations})
            if data.get("goal"):
                ap_send_queue.put({"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL})
            logger.info(f"🔄 Resincronizado con el juego: {len(locations)} ubicaciones.")
            self._send_json_response(200, {"status": "ok"})

        elif self.path == "/goal":
            if not self._server_ready():
                self._send_json_response(200, {"status": "offline"})
                return
            logger.info("🏆 ¡Juego Terminado! Informando a Archipelago...")
            ap_send_queue.put({"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL})
            self._send_json_response(200, {"status": "ok", "tracked": True})
        else:
            self._send_json_response(404, {"error": "not_found"})


def item_event(item_id: int, index: int) -> dict:
    """Traduce un ítem de AP a la acción que entiende el juego."""
    entry = ITEM_DICTIONARY.get(str(item_id))
    if entry is None:
        logger.warning(f"⚠️ Ítem AP desconocido (ID: {item_id}). Sin mapeo.")
        return {"action": "unknown", "index": index, "name": str(item_id)}
    if entry.get("type") == "badge":
        return {"action": "give_badge", "index": index, "badge_id": entry.get("badge_id", 0), "name": entry["name"]}
    return {"action": "give_item", "index": index, "item": entry.get("game_id", entry["name"].upper()),
            "quantity": 1, "name": entry["name"]}


def resolve_location(data: dict) -> dict:
    """Decide si el evento del juego es una ubicación de esta semilla.

    tracked=True: el juego no entrega el ítem original. tracked=False: lo entrega."""
    key = f"{data.get('map_id', '')}_{data.get('event_id', '')}"
    ap_ids = LOCATION_MAPPING.get(key)
    if not ap_ids:
        logger.info(f"⚠️ Ubicación {key} no encontrada en Archipelago. Entregando ítem nativo.")
        return {"status": "ok", "tracked": False}
    if not isinstance(ap_ids, list):
        ap_ids = [ap_ids]

    # Un mismo evento puede dar varios ítems: se usa el primer ID aún no marcado.
    for ap_id in ap_ids:
        if ap_id in ctx.server_locations and ap_id not in ctx.checked_locations \
                and ap_id not in ctx.locally_sent_locations:
            logger.info(f"📦 Recogido ítem en ubicación AP {key}. Enviando AP ID: {ap_id}")
            ctx.locally_sent_locations.add(ap_id)
            ap_send_queue.put({"cmd": "LocationChecks", "locations": [ap_id]})
            return {"status": "ok", "tracked": True, "location": ap_id}

    logger.info(f"⚠️ Ubicación {key} excluida por YAML o ya revisada. Entregando ítem nativo.")
    return {"status": "ok", "tracked": False}

def http_server_thread():
    server = HTTPServer((HTTP_HOST, HTTP_PORT), APRequestHandler)
    logger.info(f"Servidor HTTP escuchando en http://{HTTP_HOST}:{HTTP_PORT}")
    server.serve_forever()

class PokemonIFCommandProcessor(ClientCommandProcessor):
    def _cmd_slot(self, slot_name: str):
        """Set the player slot name for the connection"""
        self.ctx.auth = slot_name
        self.output(f"Nombre de jugador cambiado a: {slot_name}. Intenta conectarte ahora.")

    def _cmd_tracker(self):
        """Muestra información sobre cómo acceder al Tracker."""
        self.output("El enlace del tracker no se puede obtener automáticamente del servidor.")
        self.output("Por favor, dirígete a la página de tu sala (Room) en archipelago.gg para encontrar tu enlace del tracker personal.")

class PokemonIFContext(CommonContext):
    command_processor = PokemonIFCommandProcessor
    game = "Pokemon Infinite Fusion"
    items_handling = 0b111

    def __init__(self, server_address, password, auto_name=None):
        super().__init__(server_address, password)
        self.sender_task = None
        self.auto_name = auto_name
        self.locally_sent_locations = set()
        self.slot_data = {}
        if auto_name:
            self.auth = auto_name

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
            
        if not getattr(self, 'auth', None) or self.auth == "":
            # Al reconectar, CommonContext borra auth: reutilizar el último nombre válido
            if self.username or getattr(self, 'auto_name', None):
                self.auth = self.username or self.auto_name
                logger.info(f"Recuperando nombre autodetectado: {self.auth}")
            else:
                logger.info("❌ ERROR: No se encontró ningún nombre de jugador (Slot). Usa el comando /slot Nombre, y luego reconecta.")
                return
        
        logger.info(f"Intentando conectar a Archipelago con el nombre (Slot): '{self.auth}'...")
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        super().on_package(cmd, args)
        if cmd == "RoomInfo":
            self.seed_name = args.get("seed_name")
            
        elif cmd == "Connected":
            self.slot_data = args.get("slot_data") or {}
            if self.server_address and "archipelago.gg" in self.server_address:
                logger.info("💡 Recuerda que puedes encontrar tu Tracker personal en la página de la sala (Room) en archipelago.gg.")
            logger.info("¡Autenticado en Archipelago!")
            
            if "slot_data" in args:
                game_receive_queue.put({"action": "set_options", "options": args["slot_data"]})
        
        elif cmd == "ReceivedItems":
            # La base CommonClient de Archipelago ya maneja ctx.items_received.
            # No encolamos nada aquí para evitar pérdida de ítems si el cliente se cierra antes de que el juego haga poll.
            pass
                    
                    
                    
        elif cmd == "PrintJSON":
            if "data" in args:
                parts = []
                for p in args["data"]:
                    t = p.get("type")
                    text = str(p.get("text", ""))
                    if t == "player_id":
                        try:
                            player = int(text)
                            parts.append(self.player_names[player] if player in getattr(self, "player_names", {}) else text)
                        except:
                            parts.append(text)
                    elif t == "item_id":
                        try:
                            item = text
                            if item in ITEM_DICTIONARY:
                                parts.append(ITEM_DICTIONARY[item]["name"])
                            elif hasattr(self, "item_names"):
                                parts.append(self.item_names.lookup_in_game(int(text)))
                            else:
                                parts.append(text)
                        except:
                            parts.append(text)
                    elif t == "location_id":
                        try:
                            loc = text
                            if hasattr(self, "location_names"):
                                parts.append(self.location_names.lookup_in_game(int(text)))
                            else:
                                parts.append(text)
                        except:
                            parts.append(text)
                    else:
                        parts.append(text)
                
                final_text = "".join(parts).strip()
                if final_text:
                    game_receive_queue.put({
                        "action": "chat_message",
                        "text": final_text
                    })

    def run_gui(self):
        from kvui import GameManager  # type: ignore
        class PokemonIFManager(GameManager):
            logging_pairs = [
                ("Client", "Archipelago")
            ]
            base_title = "Archipelago Pokemon Infinite Fusion Client"
        self.ui = PokemonIFManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")

async def send_queue_loop(ctx: PokemonIFContext):
    while not ctx.exit_event.is_set():
        # Sin conexión el paquete se queda en la cola (antes se descartaba)
        if not ap_send_queue.empty() and ctx.server and not ctx.server.socket.closed:
            await ctx.send_msgs([ap_send_queue.get()])
        await asyncio.sleep(0.1)

def launch_game_automatically():
    game_paths = ["Game-preloaded.exe", "Game.exe", "../Game-preloaded.exe", "../Game.exe"]
    
    # Intentar leer desde las configuraciones de Archipelago
    try:
        from settings import get_settings  # type: ignore
        ap_settings = get_settings()
        
        # ap_settings puede contener "pokemon_i_f_settings" u otro nombre derivado de PokemonIFSettings
        saved_path = ""
        for key, group in ap_settings.items():
            if "pokemon_infinite_fusion" in key.lower() or type(group).__name__ == "PokemonIFSettings":
                if isinstance(group, dict):
                    saved_path = group.get("rom_file", "")
                elif hasattr(group, "rom_file"):
                    saved_path = getattr(group, "rom_file", "")
                
                if isinstance(saved_path, str) and os.path.exists(saved_path):
                    logger.info(f"Lanzando el juego desde la ruta configurada en Launcher: {saved_path}")
                    subprocess.Popen([saved_path], cwd=os.path.dirname(os.path.abspath(saved_path)) or ".")
                    return
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"No se pudo cargar la configuración de Archipelago: {e}")

    for path in game_paths:
        if os.path.exists(path):
            logger.info(f"Lanzando el juego automáticamente desde: {path}")
            subprocess.Popen([path], cwd=os.path.dirname(os.path.abspath(path)) or ".")
            return

    # Diálogo para pedir al usuario si no se encontró
    try:
        import tkinter as tk
        from tkinter import filedialog
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', 1)
        messagebox.showinfo(
            "Pokemon Infinite Fusion", 
            "No se encontró el ejecutable del juego.\nPor favor, selecciona tu archivo Game.exe o Game-preloaded.exe.", 
            parent=root
        )
        file_path = filedialog.askopenfilename(
            title="Selecciona Game.exe",
            filetypes=[("Ejecutables", "*.exe")],
            parent=root
        )
        root.destroy()
        
        if file_path:
            logger.info(f"Lanzando el juego desde la nueva ruta: {file_path}")
            subprocess.Popen([file_path], cwd=os.path.dirname(os.path.abspath(file_path)) or ".")
            
            # Intentar guardar la ruta en host.yaml
            try:
                from settings import get_settings  # type: ignore
                ap_settings = get_settings()
                for key, group in ap_settings.items():
                    if "pokemon_infinite_fusion" in key.lower() or type(group).__name__ == "PokemonIFSettings":
                        if isinstance(group, dict):
                            group["rom_file"] = file_path
                        elif hasattr(group, "rom_file"):
                            setattr(group, "rom_file", file_path)
                ap_settings.save()
                logger.info("Ruta guardada en las configuraciones de Archipelago exitosamente.")
            except Exception as e:
                pass
            return
        else:
            logger.warning("Selección cancelada. Inicia el juego de forma manual.")
    except Exception as e:
        logger.warning(f"No se pudo abrir el diálogo interactivo: {e}")
        logger.warning("No se encontró el ejecutable del juego automáticamente. Inicia el juego de forma manual.")

def launch(ap_url=None):
    auto_name = None
    if not ap_url:
        import glob
        import os
        import re
        
        # 1. Intentar autodetectar el archivo .apif más reciente en la carpeta de output
        output_dir = os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), "Archipelago", "output")
        if os.path.exists(output_dir):
            apif_files = glob.glob(os.path.join(output_dir, "*.apif"))
            if apif_files:
                apif_files.sort(key=os.path.getmtime, reverse=True)
                ap_url = apif_files[0]
                
        # 2. Si no hay .apif, leer directamente del archivo .yaml en la carpeta Players (¡Sin pasos extra!)
        if not ap_url:
            players_dir = os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), "Archipelago", "Players")
            if os.path.exists(players_dir):
                yaml_files = glob.glob(os.path.join(players_dir, "*Pokemon*.yaml")) + glob.glob(os.path.join(players_dir, "*.yaml"))
                for yaml_file in yaml_files:
                    try:
                        with open(yaml_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                            match = re.search(r'^name:\s*([^\n\r#]+)', content, re.MULTILINE)
                            if match:
                                raw_name = match.group(1).strip().strip("'").strip('"')
                                raw_name = re.sub(r'\{number\}|\{player\}', '1', raw_name, flags=re.IGNORECASE)
                                auto_name = raw_name
                                break
                    except Exception:
                        continue

    if not ap_url and not auto_name:
        try:
            import tkinter as tk
            from tkinter import filedialog
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            root.wm_attributes('-topmost', 1)
            messagebox.showinfo("Archipelago", "Por favor selecciona tu archivo de parche (.apif)", parent=root)
            file_path = filedialog.askopenfilename(
                title="Selecciona tu archivo .apif",
                filetypes=[("APIF files", "*.apif")],
                parent=root
            )
            root.destroy()
            if file_path:
                ap_url = file_path
            else:
                logger.warning("No se seleccionó ningún archivo .apif. Te conectarás sin Nombre de Jugador automático.")
        except Exception as e:
            logger.warning(f"No se pudo abrir el diálogo interactivo: {e}")
    async def main():
        global ctx
        parser = get_base_parser(description="Pokemon Infinite Fusion Client")
        args, _ = parser.parse_known_args()

        ctx = PokemonIFContext(args.connect, args.password, auto_name=auto_name)
        
        if auto_name:
            logger.info(f"Nombre de jugador autodetectado automáticamente desde YAML: {ctx.auth}")
        
        if ap_url:
            logger.info(f"Cargando archivo APIF: {ap_url}")
            try:
                with open(ap_url, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if "server" in data and data["server"]:
                        ctx.server_address = f"{data['server']}:{data.get('port', 38281)}"
                    if "slot_name" in data:
                        ctx.auth = data["slot_name"]
            except Exception as e:
                logger.error(f"Error cargando archivo APIF: {e}")

        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        ctx.sender_task = asyncio.create_task(send_queue_loop(ctx), name="sender loop")

        threading.Thread(target=http_server_thread, daemon=True).start()

        launch_game_automatically()

        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()

        await ctx.exit_event.wait()
        ctx.server_task.cancel()
        ctx.sender_task.cancel()

    colorama.init()
    asyncio.run(main())
    colorama.deinit()

if __name__ == '__main__':
    launch()
