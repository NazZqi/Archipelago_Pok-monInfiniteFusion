"""Arma la lista de archivos de arranque desde una corrida con --diagnostico.

Con --diagnostico, bloques.js manda al servidor líneas "[granos] g g ...": las partes de 64 KiB
del paquete que el juego leyó. Un archivo entra si el juego leyó el comienzo de sus datos.

Uso: arranque.py <paquete> <log> > web/arranque.txt
"""
import sys
import zipfile
from pathlib import Path

GRANO = 1 << 16
CABECERA = 30  # bloques.js la sirve del marcador: nunca queda registrada

paquete, log = Path(sys.argv[1]), Path(sys.argv[2])
granos = set()
for linea in log.read_text(encoding="utf-8", errors="replace").splitlines():
    if "[granos]" in linea:
        granos.update(int(g) for g in linea.split("[granos]", 1)[1].split("[medida]")[0].split())

with zipfile.ZipFile(paquete) as z, paquete.open("rb") as f:
    for info in sorted(z.infolist(), key=lambda i: i.header_offset):
        f.seek(info.header_offset + 26)
        nombre, extra = (int.from_bytes(f.read(2), "little") for _ in range(2))
        if info.file_size and (info.header_offset + CABECERA + nombre + extra) // GRANO in granos:
            print(info.filename)
