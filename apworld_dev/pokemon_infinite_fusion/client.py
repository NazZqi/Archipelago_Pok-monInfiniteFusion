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

import colorama

from NetUtils import ClientStatus
from CommonClient import CommonContext, server_loop, gui_enabled, ClientCommandProcessor, logger, get_base_parser

HTTP_HOST = "127.0.0.1"
HTTP_PORT = 5050

# Cola global para mensajes HTTP -> Kivy
game_receive_queue = queue.Queue()
# Cola global para mensajes Kivy -> HTTP
ap_send_queue = queue.Queue()

# Ubicaciones activas globales para la semilla actual
ACTIVE_LOCATIONS = set()
game_connected = False
last_seen = 0.0

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
    
    def do_GET(self):
        global last_seen, game_connected
        if self.path == "/poll":
            last_seen = time.time()
            if not game_connected:
                game_connected = True
                logger.info("🎮 Juego Conectado al Cliente HTTP")
                
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
                
                if msg_type == "item_found" or msg_type == "item_received":
                    map_id = str(data.get("map_id", ""))
                    event_id = str(data.get("event_id", ""))
                    key = f"{map_id}_{event_id}"
                    
                    if key in LOCATION_MAPPING:
                        ap_ids = LOCATION_MAPPING[key]
                        if not isinstance(ap_ids, list):
                            ap_ids = [ap_ids]
                        
                        # Verificar si las ubicaciones están activas en esta semilla (ej. no excluidas por yaml)
                        valid_ids = [ap_id for ap_id in ap_ids if ap_id in ACTIVE_LOCATIONS]
                        
                        if not valid_ids:
                            logger.info(f"⚠️ Ubicación {key} excluida por opciones del YAML. Entregando ítem nativo.")
                            self._send_json_response(200, {"status": "ok", "tracked": False})
                            return
                        
                        logger.info(f"📦 Recogido ítem en mapa {map_id} evento {event_id}. AP IDs: {valid_ids}")
                        ap_send_queue.put({"cmd": "LocationChecks", "locations": valid_ids})
                        self._send_json_response(200, {"status": "ok", "tracked": True})
                        return
                    else:
                        logger.info(f"⚠️ Ubicación {key} no encontrada en Archipelago. Entregando ítem nativo.")
                        self._send_json_response(200, {"status": "ok", "tracked": False})
                        return
                
                self._send_json_response(200, {"status": "ok"})
            except Exception as e:
                self._send_json_response(500, {"error": str(e)})
        elif self.path == "/goal":
            try:
                logger.info("🏆 ¡Juego Terminado! Informando a Archipelago...")
                ap_send_queue.put({"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL})
                self._send_json_response(200, {"status": "ok", "tracked": True})
            except Exception as e:
                self._send_json_response(500, {"error": str(e)})
        else:
            self._send_json_response(404, {"error": "not_found"})

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
        """Abre el Tracker del Multiworld en tu navegador web."""
        if not self.ctx.seed_name:
            self.output("Debes estar conectado a un servidor para usar este comando.")
            return
        
        if self.ctx.server_address and "archipelago.gg" in self.ctx.server_address:
            url = f"https://archipelago.gg/tracker/{self.ctx.seed_name}"
            self.output(f"Abriendo el Tracker en tu navegador: {url}")
            import webbrowser
            try:
                webbrowser.open(url)
            except Exception as e:
                self.output(f"No se pudo abrir el navegador: {e}")
        else:
            self.output("Este servidor no es archipelago.gg oficial. No se puede determinar el enlace del tracker automáticamente.")

class PokemonIFContext(CommonContext):
    command_processor = PokemonIFCommandProcessor
    game = "Pokemon Infinite Fusion"
    items_handling = 0b111

    def __init__(self, server_address, password, auto_name=None):
        super().__init__(server_address, password)
        self.sender_task = None
        self.last_received_index = -1
        self.auto_name = auto_name
        self.active_locations = set()
        if auto_name:
            self.auth = auto_name

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
            
        if not getattr(self, 'auth', None) or self.auth == "":
            if getattr(self, 'auto_name', None):
                self.auth = self.auto_name
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
            if self.server_address and "archipelago.gg" in self.server_address:
                if self.seed_name:
                    tracker_url = f"https://archipelago.gg/tracker/{self.seed_name}"
                    logger.info(f"🔗 Enlace al Tracker: {tracker_url}")
                    logger.info("💡 Abriendo el Tracker en tu navegador web automáticamente...")
                    import webbrowser
                    try:
                        webbrowser.open(tracker_url)
                    except Exception as e:
                        logger.error(f"No se pudo abrir el navegador automáticamente: {e}")
                    logger.info("💡 Consejo: Escribe /tracker en la barra inferior para abrirlo manualmente.")
            logger.info("¡Autenticado en Archipelago!")
            
            # Guardamos las ubicaciones activas para esta semilla
            global ACTIVE_LOCATIONS
            ACTIVE_LOCATIONS = set(args.get("missing_locations", [])) | set(args.get("checked_locations", []))
            
            if "slot_data" in args:
                game_receive_queue.put({"action": "set_options", "options": args["slot_data"]})
        
        elif cmd == "ReceivedItems":
            index = args.get("index", 0)
            items = args.get("items", [])
            for i, item_data in enumerate(items):
                current_idx = index + i
                if current_idx <= self.last_received_index:
                    continue
                self.last_received_index = current_idx
                
                item_id = getattr(item_data, "item", None)
                if item_id is None and isinstance(item_data, dict):
                    item_id = item_data.get("item")
                
                item_key = str(item_id)
                
                if item_key in ITEM_DICTIONARY:
                    entry = ITEM_DICTIONARY[item_key]
                    item_name = entry["name"]
                    item_type = entry.get("type", "item")
                    
                    if item_type == "badge":
                        badge_id = entry.get("badge_id", 0)
                        logger.info(f"🎁 Recibido: {item_name} (Medalla). Enviando al juego...")
                        game_receive_queue.put({
                            "action": "give_badge",
                            "badge_id": badge_id,
                            "name": item_name
                        })
                    else:
                        game_id = entry.get("game_id", item_name.upper())
                        logger.info(f"🎁 Recibido: {item_name}. Enviando al juego...")
                        game_receive_queue.put({
                            "action": "give_item",
                            "item": game_id,
                            "quantity": 1,
                            "name": item_name
                        })
                else:
                    logger.warning(f"⚠️ Ítem AP desconocido (ID: {item_id}). Sin mapeo.")
                    
        elif cmd == "PrintJSON":
            text = "".join([p.get("text", "") for p in args.get("data", [])])
            if text.strip():
                game_receive_queue.put({
                    "action": "chat_message",
                    "text": text.strip()
                })

    def run_gui(self):
        from kvui import GameManager
        class PokemonIFManager(GameManager):
            logging_pairs = [
                ("Client", "Archipelago")
            ]
            base_title = "Archipelago Pokemon Infinite Fusion Client"
        self.ui = PokemonIFManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")

async def send_queue_loop(ctx: PokemonIFContext):
    while not ctx.exit_event.is_set():
        if not ap_send_queue.empty():
            pkt = ap_send_queue.get()
            if ctx.server and not ctx.server.socket.closed:
                await ctx.send_msgs([pkt])
        await asyncio.sleep(0.1)

def launch_game_automatically():
    game_paths = ["Game-preloaded.exe", "Game.exe", "../Game-preloaded.exe", "../Game.exe"]
    
    # Intentar leer desde las configuraciones de Archipelago
    try:
        from settings import get_settings
        ap_settings = get_settings()
        
        # ap_settings puede contener "pokemon_i_f_settings" u otro nombre derivado de PokemonIFSettings
        saved_path = ""
        for key, group in ap_settings.items():
            if "pokemon" in key.lower() or type(group).__name__ == "PokemonIFSettings":
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
                from settings import get_settings
                ap_settings = get_settings()
                for key, group in ap_settings.items():
                    if "pokemon" in key.lower() or type(group).__name__ == "PokemonIFSettings":
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
