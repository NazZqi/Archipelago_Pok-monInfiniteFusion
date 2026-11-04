"""Adapta el core web de mkxp-z publicado para correr PIF. Equivale a recompilar con dos cambios.

Memoria: wasm_rt_grow_memory crece con realloc, que necesita el bloque viejo y el nuevo a
la vez. Con el heap limitado a 2 GiB falla cuando el Ruby de PIF pasa de unos 600 MB, y
llega al juego como "Sandbox trap". Se sube WASM_MIN_PAGES en binding-sandbox/wasm-rt.cpp
para reservar de una vez.

Lectura: PhysFS lee el índice del zip en cientos de miles de lecturas diminutas, y cada una
hacía un blob.slice() asíncrono: 70 s para montar el paquete. Un búfer de 1 MB lo deja en 2 s.
Tras un salto solo lee 16 KB: al abrir un archivo, PhysFS salta por la cabecera de cada entrada
de la carpeta, y traer 1 MB por cada una costaba 3 ms por entrada.

Paquete remoto: el launcher deja en OPFS un marcador JSON en vez del paquete, y el core lo
lee por bloques con Range (web/scripts/bloques.js).

Uso: parchear_core.py <carpeta del core original> <sitio>
"""
import sys
from pathlib import Path

BLOQUES = Path(__file__).parent.parent / "scripts" / "bloques.js"
CAPACIDAD = 0x48000000  # 1,125 GiB; el resto del core usa unos 430 MB
ANTES = bytes.fromhex("80 80 80 30")  # LEB128 de 96 MiB, WASM_MIN_PAGES * 64 KiB
FUNCION = 10789
# Offset en el archivo de cada constante de FUNCION: capacity, log, malloc y comparación
SITIOS = (0x14ef940, 0x14ef956, 0x14ef97e, 0x14ef991)


def leb_u(d, i):
    r = s = 0
    while True:
        b = d[i]
        i += 1
        r |= (b & 127) << s
        s += 7
        if b < 128:
            return r, i


def leb_s(v):
    out = bytearray()
    while True:
        b = v & 127
        v >>= 7
        if (v == 0 and not b & 64) or (v == -1 and b & 64):
            out.append(b)
            return bytes(out)
        out.append(b | 128)


def leb_u_fijo(v, largo):
    out = bytearray()
    for i in range(largo):
        b = v & 127
        v >>= 7
        out.append(b | 128 if i < largo - 1 else b)
    assert v == 0
    return bytes(out)


def parchear_js(origen, destino):
    js = origen.read_text(encoding="utf-8")
    lectura = ("let slice=blob.slice(pos,pos+len);let nread=0;try{let buf=await slice.arrayBuffer();"
               "let data=new Uint8Array(buf);GROWABLE_HEAP_U8().set(data,bufPtr);nread+=data.length}catch(e)")
    con_bufer = ("let nread=0;try{if(blob.leer){let d=await blob.leer(pos,len);GROWABLE_HEAP_U8().set(d,bufPtr);"
                 "nread+=d.length}else if(len<=4096&&blob.size>1e8){let c=__lecturas.get(blob);"
                 "if(c===undefined){c={b:new Uint8Array(0),p:0};__lecturas.set(blob,c)}"
                 "if(pos<c.p||pos+len>c.p+c.b.length){let n=pos>=c.p&&pos<=c.p+c.b.length?1048576:16384;"
                 "c.b=new Uint8Array(await blob.slice(pos,pos+n).arrayBuffer());c.p=pos}"
                 "let d=c.b.subarray(pos-c.p,pos-c.p+len);GROWABLE_HEAP_U8().set(d,bufPtr);nread+=d.length}"
                 "else{let buf=await blob.slice(pos,pos+len).arrayBuffer();let data=new Uint8Array(buf);"
                 "GROWABLE_HEAP_U8().set(data,bufPtr);nread+=data.length}}catch(e)")
    funcion = "async function __wasmfs_opfs_read_blob("
    # El paquete en OPFS es un marcador JSON: se lee como paquete remoto por bloques
    remoto = ('async function __remoto(a){if(!a.name.endsWith(".mkxpz")||a.size>16<<20'
              '||await a.slice(0,1).text()!=="{")return a;let p=await __paqueteRemoto.abrir('
              '{...JSON.parse(await a.text()),url:__paqueteRemoto.urlDe(a.name)});p.rellenar();return p}')
    abrir = ("let blob=await fileHandle.getFile();blobID=", "let blob=await __remoto(await fileHandle.getFile());blobID=")
    tamano = ("size=(await fileHandle.getFile()).size", "size=(await __remoto(await fileHandle.getFile())).size")
    for antes, _ in (abrir, tamano):
        assert js.count(antes) == 1, antes
    assert js.count(lectura) == 1 and js.count(funcion) == 1
    js = js.replace(lectura, con_bufer).replace(*abrir).replace(*tamano)
    previo = BLOQUES.read_text(encoding="utf-8") + remoto + "var __lecturas=new WeakMap;"
    destino.write_text(js.replace(funcion, previo + funcion), encoding="utf-8")


core, sitio = Path(sys.argv[1]), Path(sys.argv[2])
parchear_js(core / "mkxp-z_libretro.js", sitio / "mkxp-z_libretro.js")
d = bytearray((core / "mkxp-z_libretro.wasm").read_bytes())
nuevo = leb_s(CAPACIDAD)
extra = len(nuevo) - len(ANTES)

i = 8
while True:
    tipo = d[i]
    tam_sec, ini_sec = leb_u(d, i + 1)
    if tipo == 10:
        pos_tam_sec, largo_tam_sec = i + 1, ini_sec - i - 1
        break
    if tipo == 2:
        n, p = leb_u(d, ini_sec)
        importadas = 0
        for _ in range(n):
            l, p = leb_u(d, p)
            p += l
            l, p = leb_u(d, p)
            p += l
            k = d[p]
            p += 1
            if k == 0:
                _, p = leb_u(d, p)
                importadas += 1
            elif k == 1:
                p += 1
                fl = d[p]
                p += 1
                _, p = leb_u(d, p)
                if fl & 1:
                    _, p = leb_u(d, p)
            elif k == 2:
                fl = d[p]
                p += 1
                _, p = leb_u(d, p)
                if fl & 1:
                    _, p = leb_u(d, p)
            else:
                p += 2
    i = ini_sec + tam_sec

n, p = leb_u(d, ini_sec)
for f in range(importadas, importadas + n):
    tam, cuerpo = leb_u(d, p)
    if f == FUNCION:
        pos_tam, largo_tam = p, cuerpo - p
        break
    p = cuerpo + tam
assert cuerpo <= min(SITIOS) and max(SITIOS) < cuerpo + tam

for offset in reversed(SITIOS):
    assert d[offset:offset + len(ANTES)] == ANTES, hex(offset)
    d[offset:offset + len(ANTES)] = nuevo
d[pos_tam:pos_tam + largo_tam] = leb_u_fijo(tam + extra * len(SITIOS), largo_tam)
d[pos_tam_sec:pos_tam_sec + largo_tam_sec] = leb_u_fijo(tam_sec + extra * len(SITIOS), largo_tam_sec)
(sitio / "mkxp-z_libretro.wasm").write_bytes(d)
print(f"capacidad inicial {CAPACIDAD / 2**30:.3f} GiB, {len(d)} bytes")
