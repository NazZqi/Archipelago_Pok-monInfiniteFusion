"""Prueba de integración: servidor AP real + cliente PIF + juego simulado por HTTP.

Uso: bridge_test.py <AP_DIR> <seed.zip> <apif>

La semilla debe ser de un solo jugador con el YAML por defecto (la ubicación
29_8 tiene que existir). Necesita run_client.py en la misma carpeta y libres
los puertos 5050 y 38299.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

AP_DIR, SEED, APIF = sys.argv[1], sys.argv[2], sys.argv[3]
PY = str(Path(AP_DIR) / ".venv" / "Scripts" / "python.exe")
HERE = Path(__file__).parent
LOGS = Path(AP_DIR) / "TestLogs"
LOGS.mkdir(exist_ok=True)
PORT = 38299
BRIDGE = "http://127.0.0.1:5050"
ENV = dict(os.environ, SKIP_REQUIREMENTS_UPDATE="1", PYTHONIOENCODING="utf-8")


def start_server(log_name):
    log = open(LOGS / log_name, "w", encoding="utf-8")
    return subprocess.Popen([PY, "MultiServer.py", SEED, "--port", str(PORT), "--disable_save"],
                            cwd=AP_DIR, env=ENV, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)


def get(path):
    with urllib.request.urlopen(BRIDGE + path, timeout=5) as r:
        return json.loads(r.read())


def post(path, body):
    req = urllib.request.Request(BRIDGE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def wait_for(predicate, what, timeout=90):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            last = predicate()
            if last:
                return last
        except Exception as e:
            last = e
        time.sleep(1)
    raise AssertionError(f"timeout esperando {what}: {last}")


def items(poll):
    return [e for e in poll["events"] if "index" in e]


server = start_server("server1.log")
client_log = open(LOGS / "client.log", "w", encoding="utf-8")
client = subprocess.Popen([PY, str(HERE / "run_client.py"), AP_DIR, APIF, str(PORT)],
                          cwd=AP_DIR, env=ENV, stdin=subprocess.PIPE, stdout=client_log, stderr=subprocess.STDOUT)
try:
    # 1. El cliente se conecta al servidor y lo informa al juego
    poll = wait_for(lambda: (p := get("/poll?index=0&opts=1"))["ready"] and p, "ready")
    assert any(e["action"] == "set_options" for e in poll["events"]), poll
    print("OK conectado; opciones entregadas")

    # 2. Ubicación real (29_8 tiene la Poké Flauta en la semilla 7)
    r = post("/event", {"type": "item_found", "item": "X", "quantity": 1, "map_id": 29, "event_id": 8})
    assert r["tracked"] is True and isinstance(r["location"], int), r
    location = r["location"]
    print("OK check marcado:", r)

    # 3. El ítem llega con su índice, y se repite mientras el juego no avance el índice
    first = wait_for(lambda: items(get("/poll?index=0")), "ítem recibido")
    assert first[0]["index"] == 0 and first[0]["action"] == "give_item", first
    again = items(get("/poll?index=0"))
    assert again and again[0]["index"] == 0, again
    assert items(get("/poll?index=1")) == [], "con index=1 no debería repetir"
    print("OK ítem recibido y re-pedible por índice:", first[0])

    # 4. Evento sin ubicación AP y evento repetido: el juego entrega el ítem original
    assert post("/event", {"type": "item_found", "map_id": 9999, "event_id": 1})["tracked"] is False
    assert post("/event", {"type": "item_found", "map_id": 29, "event_id": 8})["tracked"] is False
    print("OK eventos no-AP / repetidos -> nativo")

    # 5. Servidor caído: el cliente responde offline y el juego guardaría el check
    server.kill(); server.wait()
    wait_for(lambda: not get("/poll?index=0")["ready"], "ready=false")
    r = post("/event", {"type": "item_found", "map_id": 29, "event_id": 8})
    assert r == {"status": "offline"}, r
    assert post("/resync", {"locations": [location]}) == {"status": "offline"}
    print("OK sin servidor -> offline (no se pierde el check)")

    # 6. Servidor nuevo sin guardado: la resincronización del juego recupera el check y su ítem
    server = start_server("server2.log")
    wait_for(lambda: get("/poll?index=0")["ready"], "ready tras reinicio")
    assert items(get("/poll?index=0")) == [], "servidor nuevo no debería tener ítems aún"
    assert post("/resync", {"locations": [location], "goal": True}) == {"status": "ok"}
    recovered = wait_for(lambda: items(get("/poll?index=0")), "ítem tras resync")
    assert recovered[0]["index"] == 0, recovered
    print("OK resync recupera el check y reentrega el ítem:", recovered[0])

    wait_for(lambda: "Goal" in (LOGS / "server2.log").read_text(encoding="utf-8", errors="replace")
             or "completed" in (LOGS / "server2.log").read_text(encoding="utf-8", errors="replace"), "meta en servidor", 30)
    print("OK meta registrada en el servidor")
    print("TODO OK")
finally:
    for p in (client, server):
        p.kill()
