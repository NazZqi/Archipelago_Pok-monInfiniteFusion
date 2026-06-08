from worlds.LauncherComponents import Component, SuffixIdentifier, components, Type, icon_paths
import asyncio
from pathlib import Path

try:
    from . import settings
except ImportError:
    import settings

def _run_client_process(ap_url):
    from .client import launch
    launch(ap_url)

def run_client(ap_url=None):
    import multiprocessing
    p = multiprocessing.Process(target=_run_client_process, args=(ap_url,))
    p.start()

components.append(
    Component(
        "Pokemon Infinite Fusion Client",
        func=run_client,
        game_name="Pokemon Infinite Fusion",
        component_type=Type.CLIENT,
        file_identifier=SuffixIdentifier(".apif"),
        cli=True
    )
)

class PokemonIFSettings(settings.Group):
    class GameExePath(settings.FilePath):
        """
        Ruta al ejecutable Game.exe o Game-preloaded.exe de Pokemon Infinite Fusion.
        Ejemplo: "C:/Juegos/Pokemon Infinite Fusion/Game-preloaded.exe"
        """
        description = "Ruta al ejecutable del juego (Game.exe)"

    rom_file: GameExePath = GameExePath("")
