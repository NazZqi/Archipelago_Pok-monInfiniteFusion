"""Prueba de jugadores visibles: servidor AP real + dos clientes PIF.

Uso: position_test.py <AP_DIR> <seed.zip> <apif jugador 1> <apif jugador 2>

La semilla debe tener dos jugadores de Pokémon Infinite Fusion. Necesita
run_client.py en la misma carpeta y libres los puertos 5050, 5051 y 38299.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

AP_DIR, SEED, APIF_A, APIF_B = sys.argv[1:5]
PY = str(Path(AP_DIR) / ".venv" / "Scripts" / "python.exe")
HERE = Path(__file__).parent
LOGS = Path(AP_DIR) / "TestLogs"
LOGS.mkdir(exist_ok=True)
PORT = 38299
ENV = dict(os.environ, SKIP_REQUIREMENTS_UPDATE="1", PYTHONIOENCODING="utf-8")


def start(args, log_name, http_port=None):
    env = dict(ENV, PIF_HTTP_PORT=str(http_port)) if http_port else ENV
    log = open(LOGS / log_name, "w", encoding="utf-8")
    return subprocess.Popen(args, cwd=AP_DIR, env=env, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)


def call(port, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data, headers)
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
        time.sleep(0.5)
    raise AssertionError(f"timeout esperando {what}: {last}")


procs = [start([PY, "MultiServer.py", SEED, "--port", str(PORT), "--disable_save"], "pos_server.log")]
procs.append(start([PY, str(HERE / "run_client.py"), AP_DIR, APIF_A, str(PORT)], "pos_client_a.log", 5050))
procs.append(start([PY, str(HERE / "run_client.py"), AP_DIR, APIF_B, str(PORT)], "pos_client_b.log", 5051))
try:
    for port in (5050, 5051):
        wait_for(lambda: call(port, "/poll?index=0")["ready"], f"cliente {port} listo")
    print("OK ambos clientes conectados")

    pos_a = {"type": "position", "map_id": 42, "x": 5, "y": 7, "dir": 2, "gender": "m"}
    pos_b = {"type": "position", "map_id": 42, "x": 9, "y": 9, "dir": 4, "gender": "f"}

    def sees(port, my_pos, other):
        players = call(port, "/position", my_pos)["players"]
        return next((p for p in players if p["x"] == other["x"] and p["y"] == other["y"]), None)

    seen_by_a = wait_for(lambda: call(5051, "/position", pos_b) and sees(5050, pos_a, pos_b), "A ve a B", 30)
    assert seen_by_a["name"] == "Rival1" and seen_by_a["gender"] == "f" and seen_by_a["dir"] == 4, seen_by_a
    seen_by_b = wait_for(lambda: sees(5051, pos_b, pos_a), "B ve a A", 30)
    assert seen_by_b["name"] == "Player1", seen_by_b
    print("OK cada jugador ve al otro:", seen_by_a, seen_by_b)

    # Movimiento: B camina un paso y A lo ve en la casilla nueva
    pos_b = dict(pos_b, x=10)
    wait_for(lambda: call(5051, "/position", pos_b) and sees(5050, pos_a, pos_b), "A ve el paso de B", 30)
    print("OK movimiento propagado")

    # Posición inválida: se ignora y A sigue viendo la última válida
    call(5051, "/position", dict(pos_b, x=11, dir=3))
    time.sleep(1.5)
    assert sees(5050, pos_a, pos_b), "una posición inválida no debe reemplazar a la válida"
    print("OK posición inválida ignorada")

    # Si B deja de enviar, desaparece tras el TTL
    wait_for(lambda: call(5050, "/position", pos_a)["players"] == [], "B desaparece", 15)
    print("OK jugador inactivo desaparece")
    print("TODO OK")
finally:
    for p in procs:
        p.kill()
