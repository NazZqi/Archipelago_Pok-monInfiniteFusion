"""Arranca el cliente de Pokémon IF sin GUI y sin lanzar el juego. Uso: run_client.py <AP_DIR> <apif> <port>"""
import os
import sys

ap_dir, apif, port = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, ap_dir)
os.chdir(ap_dir)
sys.argv = ["client", "--nogui", "--connect", f"localhost:{port}"]

import Utils

# Caché dentro del clon de prueba, sin tocar %LOCALAPPDATA%
Utils.cache_path.cached_path = os.path.join(ap_dir, "TestCache")

from worlds.pokemon_infinite_fusion import client as c

c.launch_game_automatically = lambda: None
c.launch(apif)
