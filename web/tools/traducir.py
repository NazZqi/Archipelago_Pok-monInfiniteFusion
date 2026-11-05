"""Traduce los textos de PIF al español con la API de Claude (Message Batches, 50% más barato).

Pasos, en la carpeta de trabajo <dir> (fuera del repo: lleva el texto del juego):
  traducir.py glosario <dir>         nombres oficiales en español desde los CSV de PokeAPI
  traducir.py enviar <dir> [N]       manda a traducir lo pendiente (o solo N textos, de muestra)
  traducir.py recoger <dir>          baja los lotes terminados, valida y guarda en cache.jsonl
  traducir.py armar <dir>            escribe traducciones.tsv para armar_spanish.rb

<dir>/textos.tsv sale de extraer_textos.rb. <dir>/pokeapi/*.csv son de PokeAPI (data/v2/csv).
La credencial la toma el SDK del entorno (ANTHROPIC_API_KEY): nunca va en el repo ni en el chat.
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

MODELO = "claude-opus-5-5"
POR_LOTE = 60          # textos por pedido
MAX_CHARS = 9000       # y no más de esto por pedido
# Batches: la mitad del precio normal de claude-opus-5-5 ($4 / $20 por millón)
PRECIO_ENTRADA, PRECIO_SALIDA = 2.0 / 1e6, 10.0 / 1e6
# Secciones de MessageTypes que son nombres sueltos: van directo al glosario si coinciden
SECCIONES_NOMBRE = {"1": "especie", "5": "movimiento", "7": "objeto", "10": "habilidad", "12": "tipo"}
CSV_GLOSARIO = {"pokemon_species_names": "pokemon_species_id", "move_names": "move_id", "item_names": "item_id",
                "ability_names": "ability_id", "type_names": "type_id", "nature_names": "nature_id"}
INGLES, ESPANOL = "9", "7"  # local_language_id de PokeAPI
# Códigos que el juego interpreta: deben quedar iguales en la traducción
# Los de Essentials van pegados a la palabra siguiente ("\rWe", "\GIt"): por eso la lista cerrada.
CODIGOS = re.compile(r"\\(?:pn|pm|pg|wtnp|wt|wu|wm|ts|op|cl|ff|ch|se|me|dxn|xn|ar|sh|ss|nr|ac|g|n|r|b|i|u|l|f|c|v)"
                     r"(?:\[[^\]]*\])?|\{\d+\}|<<[^>]*>>|<[^<>]*>|%[a-z]", re.IGNORECASE)

SISTEMA = """Traduces al español los textos de Pokémon Infinite Fusion, un fangame de Pokémon.

- Español latinoamericano neutro, natural y con el tono del original (humor, personajes, jerga de videojuego). Tuteo.
- Usa los nombres oficiales en español de Pokémon, movimientos, objetos, habilidades y tipos. El pedido trae un glosario con los que aparecen; respétalo.
- Los nombres propios de personajes y lugares del fangame se mantienen salvo que tengan nombre oficial en español.
- Copia exactamente todo código de control, sin traducirlo: \\PN, \\G, \\V[5], \\C[1], \\wtnp[30], \\wt, \\ts, \\n, \\r, \\b, {1}, <<n>>, <<r>>, <<[>>, etiquetas como <b> </b> <ac> <br>, y %p. Los códigos de una letra van pegados a la palabra que sigue ("\\rWe are" → "\\rNosotros somos"): copia el código y traduce la palabra. Puedes mover un código dentro de la frase si el español lo pide, pero no quitar ni agregar ninguno. Si un texto es solo código o un nombre que no se traduce, devuélvelo igual.
- Mantén mayúsculas iniciales, signos y saltos (<<n>>) como en el original. Agrega los signos de apertura ¿ ¡.
- Devuelve cada texto con su mismo "i"."""

ESQUEMA = {"type": "object", "additionalProperties": False, "required": ["textos"],
           "properties": {"textos": {"type": "array", "items": {
               "type": "object", "additionalProperties": False, "required": ["i", "t"],
               "properties": {"i": {"type": "integer"}, "t": {"type": "string"}}}}}}


def leer_textos(d):
    filas = [l.split("\t", 2) for l in (d / "textos.tsv").read_text(encoding="utf-8").split("\n") if l]
    return filas  # [sección, clave, original]


def glosario(d):
    nombres = {}
    for archivo, campo in CSV_GLOSARIO.items():
        por_id = {}
        with open(d / "pokeapi" / f"{archivo}.csv", encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                por_id.setdefault(fila[campo], {})[fila["local_language_id"]] = fila["name"].strip()
        for idiomas in por_id.values():
            if INGLES in idiomas and ESPANOL in idiomas:
                nombres[idiomas[INGLES]] = idiomas[ESPANOL]
    (d / "glosario.json").write_text(json.dumps(nombres, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(nombres)} nombres en el glosario")


def cache(d):
    archivo = d / "cache.jsonl"
    if not archivo.exists():
        return {}
    return {x["o"]: x for x in map(json.loads, archivo.read_text(encoding="utf-8").splitlines())}


def pendientes(d):
    """Originales únicos, en orden de aparición, que no están en caché ni salen del glosario."""
    hechos, nombres = cache(d), json.loads((d / "glosario.json").read_text(encoding="utf-8"))
    vistos, lista = set(), []
    for seccion, _, original in leer_textos(d):
        if original in vistos or original in hechos:
            continue
        vistos.add(original)
        if not (seccion in SECCIONES_NOMBRE and original in nombres):
            lista.append(original)
    return lista


def lotes(textos):
    actual, largo = [], 0
    for t in textos:
        if actual and (len(actual) >= POR_LOTE or largo + len(t) > MAX_CHARS):
            yield actual
            actual, largo = [], 0
        actual.append(t)
        largo += len(t)
    if actual:
        yield actual


def enviar(d, cuantos=None):
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    nombres = json.loads((d / "glosario.json").read_text(encoding="utf-8"))
    largos = sorted((n for n in nombres if len(n) >= 4), key=len, reverse=True)
    textos = pendientes(d)
    if cuantos:
        textos = textos[::max(1, len(textos) // cuantos)][:cuantos]  # muestra repartida por todo el juego
    pedidos, indice = [], {}
    for n, lote in enumerate(lotes(textos)):
        junto = "\n".join(lote)
        presentes = {k: nombres[k] for k in largos if k in junto}
        contenido = json.dumps({"glosario": presentes, "textos": [{"i": i, "t": t} for i, t in enumerate(lote)]},
                               ensure_ascii=False)
        cid = f"lote-{n}"
        indice[cid] = lote
        pedidos.append(Request(custom_id=cid, params=MessageCreateParamsNonStreaming(
            model=MODELO, max_tokens=32000,
            system=[{"type": "text", "text": SISTEMA, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": ESQUEMA}},
            messages=[{"role": "user", "content": contenido}])))
    lote = anthropic.Anthropic().messages.batches.create(requests=pedidos)
    with open(d / "lotes.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": lote.id, "indice": indice}, ensure_ascii=False) + "\n")
    print(f"lote {lote.id}: {len(pedidos)} pedidos, {len(textos)} textos, {sum(map(len, textos))} caracteres")


def valido(original, traduccion):
    return isinstance(traduccion, str) and traduccion.strip() and \
        Counter(CODIGOS.findall(original)) == Counter(CODIGOS.findall(traduccion))


def recoger(d):
    import anthropic
    cliente = anthropic.Anthropic()
    archivo_lotes = d / "lotes.jsonl"
    registros = [json.loads(l) for l in archivo_lotes.read_text(encoding="utf-8").splitlines()]
    hechos = cache(d)
    entrada = salida = 0
    quedan = []
    with open(d / "cache.jsonl", "a", encoding="utf-8") as f:
        for reg in registros:
            if cliente.messages.batches.retrieve(reg["id"]).processing_status != "ended":
                quedan.append(reg)
                print(f"{reg['id']}: todavía en proceso")
                continue
            for r in cliente.messages.batches.results(reg["id"]):
                lote = reg["indice"][r.custom_id]
                if r.result.type != "succeeded":
                    print(f"{r.custom_id}: {r.result.type}; queda pendiente para otro envío")
                    continue
                msg = r.result.message
                entrada += msg.usage.input_tokens + (msg.usage.cache_read_input_tokens or 0) \
                    + (msg.usage.cache_creation_input_tokens or 0)
                salida += msg.usage.output_tokens
                if msg.stop_reason != "end_turn":
                    print(f"{r.custom_id}: stop_reason {msg.stop_reason}; queda pendiente")
                    continue
                texto = next((b.text for b in msg.content if b.type == "text"), "")
                try:
                    vuelta = {x["i"]: x["t"] for x in json.loads(texto)["textos"]}
                except (json.JSONDecodeError, KeyError, TypeError):
                    print(f"{r.custom_id}: respuesta ilegible; queda pendiente")
                    continue
                for i, original in enumerate(lote):
                    if original in hechos:
                        continue
                    t = vuelta.get(i)
                    ok = valido(original, t)
                    hechos[original] = {"o": original, "t": t if ok else original, "ok": bool(ok)}
                    f.write(json.dumps(hechos[original], ensure_ascii=False) + "\n")
    archivo_lotes.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in quedan), encoding="utf-8")
    malos = sum(not x["ok"] for x in hechos.values())
    print(f"en caché: {len(hechos)} textos ({malos} quedan en inglés por códigos que no coinciden)")
    if entrada or salida:
        costo = entrada * PRECIO_ENTRADA + salida * PRECIO_SALIDA
        print(f"esta recogida: {entrada} tokens de entrada, {salida} de salida, unos US${costo:.2f}")


def armar(d):
    hechos, nombres = cache(d), json.loads((d / "glosario.json").read_text(encoding="utf-8"))
    lineas, faltan = [], 0
    for seccion, _, original in leer_textos(d):
        if seccion in SECCIONES_NOMBRE and original in nombres:
            espanol = nombres[original]
        elif original in hechos:
            espanol = hechos[original]["t"]
        else:
            faltan += 1
            continue
        lineas.append(f"{original}\t{espanol}")
    # newline="\n": en Windows write_text pone \r\n, y armar_spanish.rb separa por \n
    (d / "traducciones.tsv").write_text("\n".join(dict.fromkeys(lineas)), encoding="utf-8", newline="\n")
    print(f"traducciones.tsv: {len(set(lineas))} textos; {faltan} sin traducir (quedan en inglés)")


if __name__ == "__main__":
    orden, carpeta = sys.argv[1], Path(sys.argv[2])
    {"glosario": lambda: glosario(carpeta), "recoger": lambda: recoger(carpeta), "armar": lambda: armar(carpeta),
     "enviar": lambda: enviar(carpeta, int(sys.argv[3]) if len(sys.argv) > 3 else None)}[orden]()
