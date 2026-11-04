"""Genera el paquete web del juego y adapta el launcher publicado de mkxp-z.

El paquete no entra al repo: lleva los archivos del juego.

Uso: empaquetar.py <carpeta del juego> <sitio> --sprites <hojas base> --cache <reducidos>
     [--arranque web/arranque.txt] [--diagnostico]
<sitio> es la carpeta con el launcher y el core ya parcheado (parchear_core.py).

Junto al paquete deja pif-<hash>.json, el marcador que el launcher guarda en lugar del
paquete: con él, el core lee el paquete por bloques (web/scripts/bloques.js). --arranque
lista los archivos que el juego lee al iniciar (arranque.py): van primero y se bajan antes.
"""
import argparse
import base64
import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import oxipng
from PIL import Image

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
REMOTOS = SCRIPTS.parent.parent / "pokemon/Data/Scripts/998_Experimental/ArchipelagoRemotePlayers.rb"
SKIP_DIR = {".git", "REQUIRED_BY_INSTALLER_UPDATER"}
SKIP_EXT = {".exe", ".dll", ".bat", ".sh", ".lnk"}
# Ningún script ni evento los lee
SKIP_ARCHIVOS = {"Data/messages_fr.dat", "Data/attacksRS.dat", "Data/Sprite Credits.csv"}
PRIMER_SCRIPT = "Data/Scripts/001_Settings.rb"
HOJAS_BASE = "Graphics/CustomBattlers/spritesheets/spritesheets_base/"
HOJAS_AUTOGEN = "Graphics/Battlers/spritesheets_autogen/"
ALTO_TIRA = 5 * 96  # web_final.rb lee estas tiras: FILAS_TIRA
KBPS_BGM = 96
BLOQUE = 1 << 18     # bloques.js: BLOQUE
CLAVE_DAT = bytes.fromhex("4a8f2ce173b5960d5ea23fc781146bd9")  # Encryption::ENCRYPTION_KEY
MENSAJES = "Data/messages.dat"
STRING_VACIO = b'I"\x00\x06;\x07T'  # "" en Marshal; \x07 es el enlace al símbolo de encoding
# Sprites custom, que no van en el paquete: su lista y sus entradas de Pokédex. PIF exige los
# archivos, y dex.json son 19 MB que el parser en Ruby tardaría 23 s en leer por cada entrada.
VACIOS = {"Data/sprites/CUSTOM_SPRITES": b"", "Data/pokedex/dex.json": b"[]"}
# A, D, Q, S, W, X, Z, Space y Shift: el core los ata a botones aunque no haya mando
ESCANCODES_LIBRES = (4, 7, 20, 22, 26, 27, 29, 44, 225, 229)
# PIF corre en Ruby 3.1 y el core en 3.3: el modo 3.1 restaura lo eliminado (File.exists?, etc.)
MKXP_JSON = json.dumps({"syntaxTransform": 1, "syntaxTransformCustomVersionMajor": 3,
                        "syntaxTransformCustomVersionMinor": 1, "syntaxTransformCustomVersionTeeny": 0,
                        "pathCache": False})  # lo reemplaza WebRutas en web_compat.rb


def reducir_audio(origen, destino):
    if destino.exists():
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".tmp" + destino.suffix)
    codec = ["-c:a", "libvorbis", "-q:a", "2"] if destino.suffix == ".ogg" else ["-b:a", f"{KBPS_BGM}k"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(origen), "-map", "0:a", *codec, str(temporal)],
                   check=True)
    temporal.replace(destino)


def guardar(destino, datos):
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".tmp")
    temporal.write_bytes(datos)
    temporal.replace(destino)


def reducir_png(origen, destino):
    if destino.exists():
        return
    datos = origen.read_bytes()
    if not datos.startswith(b"\x89PNG"):  # Un WebP con nombre .png: stb_image no lo lee
        crudo = io.BytesIO()
        Image.open(io.BytesIO(datos)).save(crudo, "PNG")
        datos = crudo.getvalue()
    guardar(destino, oxipng.optimize_from_memory(datos, level=2))


def partir_hoja(origen, carpeta):
    # Decodificar una hoja cuesta 800 ms en el navegador, y el juego solo usa una celda de 96×96
    hoja = Image.open(origen)
    tiras = []
    for i, y in enumerate(range(0, hoja.height, ALTO_TIRA)):
        destino = carpeta / f"{origen.stem}_{i}.png"
        tiras.append(destino)
        if destino.exists():
            continue
        tira = hoja.convert("RGBA").crop((0, y, hoja.width, min(y + ALTO_TIRA, hoja.height)))
        crudo = io.BytesIO()
        tira.save(crudo, "PNG", compress_level=1)
        datos = oxipng.optimize_from_memory(crudo.getvalue(), level=2)
        assert Image.open(io.BytesIO(datos)).convert("RGBA").tobytes() == tira.tobytes(), destino
        guardar(destino, datos)
    return tiras


def sha256(ruta):
    digest = hashlib.sha256()
    with open(ruta, "rb") as f:
        while bloque := f.read(1 << 20):
            digest.update(bloque)
    return digest.hexdigest()


def descifrar_dat(datos):
    # PIF descifra byte a byte en Ruby: 45 s solo con messages.dat. web_final.rb lo apaga.
    largo = len(datos)
    clave = (CLAVE_DAT * (largo // len(CLAVE_DAT) + 1))[:largo]
    claro = (int.from_bytes(datos, "little") ^ int.from_bytes(clave, "little")).to_bytes(largo, "little")
    return claro if claro[:2] == b"" else datos


def quitar_vacios(mensajes):
    # 4 arrays de un millón de "" crean 4 millones de objetos: 8 s al arrancar y 25 MB. Messages#get
    # da lo mismo con nil. Solo rachas: los OrderedHash guardan blobs de largo fijo con "" adentro.
    patron = b"(?:" + re.escape(STRING_VACIO) + b"){100,}"
    limpio = re.sub(patron, lambda m: b"0" * (len(m[0]) // len(STRING_VACIO)), mensajes)
    assert len(limpio) < len(mensajes) / 2
    return limpio


def fijo(nombre):
    # Sin la hora actual, el mismo contenido da el mismo hash y nadie vuelve a bajarlo
    return zipfile.ZipInfo(nombre, (1980, 1, 1, 0, 0, 0))


def crear_paquete(juego, sprites, cache, salida, arranque, diagnostico):
    bgm = juego / "Audio/BGM"
    audio = {p: cache / p.relative_to(juego) for p in [*bgm.rglob("*.mp3"), *(juego / "Audio/ME").rglob("*.mp3")]}
    audio |= {p: (cache / p.relative_to(juego)).with_suffix(".ogg") for p in bgm.rglob("*.wav")}
    hojas = sorted((juego / HOJAS_AUTOGEN).glob("*.png"))
    imagenes = {p: cache / p.relative_to(juego) for p in (juego / "Graphics").rglob("*.png")
                if p.parent != juego / HOJAS_AUTOGEN}
    imagenes |= {p: cache / HOJAS_BASE / p.name for p in sprites.glob("*.png")}
    with ThreadPoolExecutor(8) as hilos:
        list(hilos.map(lambda par: reducir_audio(*par), audio.items()))
        list(hilos.map(lambda par: reducir_png(*par), imagenes.items()))
        tiras = dict(zip(hojas, hilos.map(lambda hoja: partir_hoja(hoja, cache / HOJAS_AUTOGEN), hojas)))
    reducidos = audio | imagenes

    compat = (SCRIPTS / "web_compat.rb").read_bytes()
    if diagnostico:
        compat += (SCRIPTS / "web_diag.rb").read_bytes()
    # Los archivos de arranque van juntos al principio: se bajan en menos bloques. Se comparan
    # sin extensión porque el audio reducido cambia de extensión; una hoja autogenerada entra
    # si alguna de sus tiras está en la lista.
    claves = {Path(nombre).with_suffix("").as_posix() for nombre in arranque}
    claves |= {Path(clave).parent.as_posix() for clave in claves}
    orden = sorted(juego.rglob("*"),
                   key=lambda r: (r.relative_to(juego).with_suffix("").as_posix() not in claves, r))
    n = 0
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for ruta in orden:
            rel = ruta.relative_to(juego)
            if (not ruta.is_file() or rel.parts[0] in SKIP_DIR or ruta.suffix.lower() in SKIP_EXT
                    or rel.as_posix() in SKIP_ARCHIVOS):
                continue
            if rel.as_posix() in VACIOS:
                z.writestr(fijo(rel.as_posix()), VACIOS[rel.as_posix()])
            elif rel.as_posix() == PRIMER_SCRIPT:
                z.writestr(fijo(rel.as_posix()), compat + ruta.read_bytes())
            elif rel.as_posix() == MENSAJES:
                z.writestr(fijo(rel.as_posix()), quitar_vacios(descifrar_dat(ruta.read_bytes())))
            elif rel.parent.as_posix() == "Data" and ruta.suffix.lower() == ".dat":
                z.writestr(fijo(rel.as_posix()), descifrar_dat(ruta.read_bytes()))
            elif ruta in tiras:
                # Una carpeta por hoja: PhysFS lee la cabecera de cada archivo de la carpeta que abre
                for i, tira in enumerate(tiras[ruta]):
                    z.write(tira, f"{HOJAS_AUTOGEN}{ruta.stem}/{i}.png")
                n += len(tiras[ruta]) - 1
            else:
                # Un audio reducido puede ser mayor si el original ya era pequeño
                reducido = reducidos.get(ruta)
                if reducido and (ruta in imagenes or reducido.stat().st_size < ruta.stat().st_size):
                    z.write(reducido, reducido.relative_to(cache).as_posix())
                else:
                    z.write(ruta, rel.as_posix())
            n += 1
        z.write(SCRIPTS / "web_final.rb", "Data/Scripts/998_Web/web_final.rb")
        # Jugadores visibles: el dibujo es el del mod de Archipelago, el puente es web_red.rb
        z.write(REMOTOS, "Data/Scripts/998_Web/red_jugadores.rb")
        z.write(SCRIPTS / "web_red.rb", "Data/Scripts/998_Web/red_puente.rb")
        n += 3
        for hoja in sorted(sprites.glob("*.png")):
            z.write(reducidos[hoja], HOJAS_BASE + hoja.name)
            n += 1
        z.writestr(fijo("mkxp.json"), MKXP_JSON)
        z.writestr(fijo("Data/web_rutas.txt"), "\n".join(z.namelist()))
    return n


def crear_marcador(paquete, arranque, diagnostico):
    # El core lee la cabecera local de cada archivo de una carpeta al abrir uno: el marcador las
    # trae completas (con nombre y extra), y abrir un archivo no baja un bloque por cada vecino
    with zipfile.ZipFile(paquete) as z, paquete.open("rb") as f:
        infos = sorted(z.infolist(), key=lambda i: i.header_offset)
        central = z.start_dir
        cabeceras = bytearray()
        for info in infos:
            f.seek(info.header_offset)
            cabecera = f.read(30)
            assert cabecera.startswith(b"PK\x03\x04"), info.filename
            largo = int.from_bytes(cabecera[26:28], "little") + int.from_bytes(cabecera[28:30], "little")
            cabeceras += cabecera + f.read(largo)
    fines = [i.header_offset for i in infos[1:]] + [central]
    bloques = set()
    for info, fin in zip(infos, fines):
        if info.filename in arranque:
            bloques.update(range(info.header_offset // BLOQUE, (fin - 1) // BLOQUE + 1))
    return json.dumps({"nombre": paquete.name, "size": paquete.stat().st_size, "central": central,
                       "arranque": sorted(bloques), "posiciones": [i.header_offset for i in infos],
                       "cabeceras": base64.b64encode(cabeceras).decode(), "diag": diagnostico},
                      separators=(",", ":")).encode()


def sustituir(js, patron, nuevo):
    js, n = re.subn(patron, lambda _: nuevo, js)
    assert n == 1, (patron, n)
    return js


def adaptar_launcher(sitio, paquete, marcador, diagnostico):
    # El launcher trae fijos la URL, el tamaño y el hash de su juego de ejemplo, y guarda
    # el core en IndexedDB por hash: sin actualizarlos seguiría usando el anterior.
    launcher = next((sitio / "assets").glob("index-*.js"))
    original = launcher.with_suffix(".orig")
    if not original.exists():
        shutil.copy(launcher, original)
    js = original.read_text(encoding="utf-8")

    core, wasm = sitio / "mkxp-z_libretro.js", sitio / "mkxp-z_libretro.wasm"
    js = sustituir(js, r"\./knight-blade-howling-of-kerberos\.mkxpz", f"./{paquete.name}")
    # En OPFS queda el marcador, no el paquete: el launcher compara contra su tamaño
    js = sustituir(js, r"\bwn=22882414\b", f"wn={marcador.stat().st_size}")
    js = sustituir(js, r"\bDn=`[0-9a-f]{64}`", f"Dn=`{sha256(marcador)}`")
    js = sustituir(js, r"\bSn=\d+,Cn=\d+", f"Sn={core.stat().st_size},Cn={wasm.stat().st_size}")
    js = sustituir(js, r"\bTn=`[0-9a-f]{64}`", f"Tn=`{sha256(core)}`")
    js = sustituir(js, r"\bEn=`[0-9a-f]{64}`", f"En=`{sha256(wasm)}`")
    js = js.replace("KNight-Blade: Howling of Kerberos", "Infinite Fusion")

    # Atajos de RetroArch sobre teclas que el jugador usa para escribir su nombre
    for atajo in ("input_toggle_fast_forward", "input_hold_fast_forward",
                  "input_toggle_slowmotion", "input_hold_slowmotion"):
        js, n = re.subn(atajo + r":`[a-z]+`", atajo + ":`nul`", js)  # Nostalgist y launcher
        assert n, atajo
    # Las letras quedan libres para escribir; el juego las lee en web_compat.rb
    js = sustituir(js, r"input_player1_a:`c`", "input_player1_a:`enter`")
    js = sustituir(js, r"input_player1_b:`x`", "input_player1_b:`escape`")
    for boton in ("x", "y", "l3", "r3", "l", "r", "r2"):
        js = sustituir(js, rf"input_player1_{boton}:`[a-z]+`", f"input_player1_{boton}:`nul`")
    sin_boton = ",".join(f'"mkxp-z_scancode-{n}":`none`' for n in ESCANCODES_LIBRES)
    js = sustituir(js, r'retroarchCoreConfig:\{"mkxp-z_saveStateSize":`256`',
                   'retroarchCoreConfig:{"mkxp-z_saveStateSize":`256`,' + sin_boton)

    bajada = "i=await(await fetch(n).then(O({onProgress:t=>{Bn+=t.transferred-e,e=t.transferred,Hn(),Rn!==null&&(In.stop(),Rn.style.display=`initial`)}}))).blob()"
    assert js.count(bajada) == 1
    js = js.replace(bajada, "i=n===bn?await window.__bajarJuego(n,t=>{Bn+=t,Hn(),Rn!==null&&(In.stop(),Rn.style.display=`initial`)}):" + bajada[2:])

    # El búfer del canvas se fija una vez al arrancar: sin esto, al cambiar la ventana la imagen
    # se estira. Se espera a que el usuario termine de arrastrar.
    inicio = "postRun(){this.resize(this.canvasInitialSize);"
    assert js.count(inicio) == 1
    js = js.replace(inicio, "postRun(){let t;addEventListener(`resize`,()=>{clearTimeout(t);"
                            "t=setTimeout(()=>this.resize(this.getElementSize()),200)});"
                            "this.resize(this.canvasInitialSize);")

    copia = "await r.write(i),await r.close(),i=await n.getFile()"
    assert js.count(copia) == 1
    js = js.replace(copia, copia + ",await window.__borrarViejos?.()")

    # juego.js guarda la consola del core para los reportes de fallos
    imprimir = "printErr(...e){console.error(...e)}"
    assert js.count(imprimir) == 1
    registro = "printErr(...e){console.error(...e);var t=e.join(` `);window.__registrarConsola?.(t);"
    if diagnostico:
        # Con #auto arranca sin gesto, y los registros del core llegan a /log
        gesto = "!navigator.userActivation.hasBeenActive"
        assert js.count(gesto) == 1
        js = js.replace(gesto, "(!location.hash.startsWith(`#auto`)&&" + gesto + ")")
        registro += ("/web-|Fatal|Aborted|Sandbox|mkxp-z|rror/.test(t)&&"
                     "fetch(`/log`,{method:`POST`,body:(window.__tag||``)+t,keepalive:!0});")
    else:
        # Lo que se publica lleva título neutro: el sitio se sirve tras login, pero queda en el historial
        pagina = sitio / "index.html"
        html = sustituir(pagina.read_text(encoding="utf-8"), r"<title>[^<]*</title>", "<title>Cinderlink · Juego</title>")
        pagina.write_text(html, encoding="utf-8")
    js = js.replace(imprimir, registro + "}")
    previo = "".join((SCRIPTS / nombre).read_text(encoding="utf-8")
                     for nombre in ("bloques.js", "bajar_juego.js", "juego.js"))
    launcher.write_text(previo + js, encoding="utf-8")


def main():
    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("juego", type=Path)
    args.add_argument("sitio", type=Path)
    args.add_argument("--sprites", type=Path, required=True)
    args.add_argument("--cache", type=Path, required=True)
    args.add_argument("--arranque", type=Path)
    args.add_argument("--diagnostico", action="store_true")
    a = args.parse_args()

    arranque = set(a.arranque.read_text(encoding="utf-8").splitlines()) if a.arranque else set()
    temporal = a.sitio / "pif.mkxpz.tmp"
    n = crear_paquete(a.juego, a.sprites, a.cache, temporal, arranque, a.diagnostico)
    paquete = a.sitio / f"pif-{sha256(temporal)[:12]}.mkxpz"
    for viejo in [*a.sitio.glob("pif-*.mkxpz"), *a.sitio.glob("pif-*.json")]:
        viejo.unlink()
    temporal.replace(paquete)
    marcador = paquete.with_suffix(".json")
    marcador.write_bytes(crear_marcador(paquete, arranque, a.diagnostico))
    adaptar_launcher(a.sitio, paquete, marcador, a.diagnostico)
    bloques = len(json.loads(marcador.read_bytes())["arranque"])
    print(f"{paquete.name}: {n} archivos, {paquete.stat().st_size / 1e6:.0f} MB; arranque {bloques * BLOQUE / 2**20:.0f} MiB")


if __name__ == "__main__":
    main()
