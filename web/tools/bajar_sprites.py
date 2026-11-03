"""Baja las hojas de sprites base que el juego nativo pide a infinitefusion.net al usarlas.

En la web no hay HTTPLite: sin estas hojas cada Pokémon sin fusionar se ve como "?".

Uso: bajar_sprites.py <carpeta destino>
"""
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://infinitefusion.net/customsprites/spritesheets/spritesheets_base/{}.png"
NB_POKEMON = 576  # Settings::NB_POKEMON
PAUSA = 0.2  # servidor ajeno: una petición a la vez

destino = Path(sys.argv[1])
destino.mkdir(parents=True, exist_ok=True)
faltan = []
for n in range(1, NB_POKEMON + 1):
    archivo = destino / f"{n}.png"
    if archivo.exists():
        continue
    pedido = urllib.request.Request(URL.format(n), headers={"User-Agent": "mkxp-z"})
    try:
        with urllib.request.urlopen(pedido, timeout=30) as r:
            datos = r.read()
    except urllib.error.HTTPError as e:
        faltan.append((n, e.code))
        continue
    # Un error del servidor no debe entrar al paquete como si fuera una imagen
    if datos[:4] != b"\x89PNG":
        faltan.append((n, "no es PNG"))
        continue
    archivo.write_bytes(datos)
    time.sleep(PAUSA)

print(f"{len(list(destino.glob('*.png')))} hojas; sin bajar: {faltan}")
