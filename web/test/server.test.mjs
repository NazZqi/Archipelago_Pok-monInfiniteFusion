// Pruebas de web/server.mjs con un Nextcloud simulado. Correr: node --test web/test/
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtemp, mkdir, writeFile, readFile, readdir, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { crearServidor, limpiarPokemon } from '../server.mjs';

const ORIGEN = 'https://juego.test';
// Cuentas del Nextcloud simulado. Como el real, no incluye `enabled` al consultar el propio usuario.
const CUENTAS = {
  ana: { clave: 'clave-ana', data: { id: 'ana', displayname: 'Ana' } },
  beto: { clave: 'clave-beto', data: { id: 'beto', displayname: 'Beto' } },
  nuevo: { clave: 'clave-nuevo', data: { id: 'nuevo', displayname: 'Nuevo', enabled: false } },
};

let nube, servidor, base, datos, juego;
const sesiones = {};

const escuchar = (srv) => new Promise((ok) => srv.listen(0, '127.0.0.1', () => ok(`http://127.0.0.1:${srv.address().port}`)));

const pedir = (ruta, { usuario, headers = {}, ...op } = {}) => fetch(base + ruta, {
  ...op,
  headers: { Origin: ORIGEN, ...(usuario && { Cookie: sesiones[usuario] }), ...headers },
});
const entrar = (usuario, clave) => pedir('/api/login', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ usuario, clave }),
});
const partida = (texto) => Buffer.concat([Buffer.from([0x04, 0x08]), Buffer.from(texto)]);
const subir = (usuario, nombre, cuerpo, version) => pedir('/api/archivos/' + encodeURIComponent(nombre), {
  method: 'PUT', usuario, body: cuerpo, headers: { 'If-Match': `"${version}"` },
});

before(async () => {
  nube = http.createServer((req, res) => {
    const [u, c] = Buffer.from((req.headers.authorization || '').replace(/^Basic /, ''), 'base64').toString().split(':');
    const cuenta = CUENTAS[u];
    if (req.url !== '/ocs/v2.php/cloud/user?format=json' || req.headers['ocs-apirequest'] !== 'true') { res.writeHead(400); return res.end(); }
    if (!cuenta || cuenta.clave !== c) { res.writeHead(401); return res.end(); }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ocs: { meta: { status: 'ok', statuscode: 200 }, data: cuenta.data } }));
  });
  const urlNube = await escuchar(nube);
  const tmp = await mkdtemp(path.join(os.tmpdir(), 'pif-server-'));
  datos = path.join(tmp, 'datos');
  juego = path.join(tmp, 'juego');
  await mkdir(juego);
  await writeFile(path.join(juego, 'pif-x.mkxpz'), Buffer.from(Array.from({ length: 256 }, (_, i) => i)));
  await writeFile(path.join(tmp, 'secreto.txt'), 'no');
  servidor = crearServidor({ nextcloud: urlNube, datos, juego, publico: path.join(tmp, 'public'), origen: ORIGEN });
  base = await escuchar(servidor);
  for (const u of ['ana', 'beto']) {
    const r = await entrar(u, CUENTAS[u].clave);
    assert.equal(r.status, 200);
    sesiones[u] = r.headers.getSetCookie()[0].split(';')[0];
  }
});

after(async () => {
  servidor.closeAllConnections();
  await new Promise((ok) => servidor.close(ok));
  await new Promise((ok) => nube.close(ok));
  await rm(path.dirname(datos), { recursive: true, force: true });
});

test('login correcto entrega cookie HttpOnly, Secure y SameSite=Strict', async () => {
  const r = await entrar('ana', 'clave-ana');
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { uid: 'ana', nombre: 'Ana' });
  const cookie = r.headers.getSetCookie()[0];
  assert.match(cookie, /^pif_sesion=[\w-]{20,};/);
  for (const atributo of ['HttpOnly', 'Secure', 'SameSite=Strict']) assert.ok(cookie.includes(atributo), atributo);
});

test('cuenta sin aprobar y clave mala no entran', async () => {
  const r = await entrar('nuevo', 'clave-nuevo');
  assert.equal(r.status, 403);
  assert.equal(r.headers.getSetCookie().length, 0);
  assert.equal((await entrar('ana', 'mala')).status, 401);
});

test('escrituras sin Origin propio se rechazan', async () => {
  const r = await pedir('/api/login', { method: 'POST', headers: { Origin: 'https://malo.test' }, body: '{}' });
  assert.equal(r.status, 403);
});

test('/juego/ pide sesión, acepta Range y manda cabeceras privadas y COOP/COEP', async () => {
  assert.equal((await pedir('/juego/pif-x.mkxpz')).status, 401);
  const r = await pedir('/juego/pif-x.mkxpz', { usuario: 'ana', headers: { Range: 'bytes=10-19' } });
  assert.equal(r.status, 206);
  assert.equal(r.headers.get('content-range'), 'bytes 10-19/256');
  assert.match(r.headers.get('cache-control'), /\bprivate\b/);
  assert.equal(r.headers.get('cross-origin-opener-policy'), 'same-origin');
  assert.equal(r.headers.get('cross-origin-embedder-policy'), 'require-corp');
  assert.deepEqual([...new Uint8Array(await r.arrayBuffer())], [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]);
  const cola = await pedir('/juego/pif-x.mkxpz', { usuario: 'ana', headers: { Range: 'bytes=-2' } });
  assert.deepEqual([...new Uint8Array(await cola.arrayBuffer())], [254, 255]);
  assert.equal((await pedir('/juego/pif-x.mkxpz', { usuario: 'ana', headers: { Range: 'bytes=300-' } })).status, 416);
  assert.equal((await pedir('/juego/..%2Fsecreto.txt', { usuario: 'ana' })).status, 403);
});

test('el archivo de un usuario no llega a otro', async () => {
  assert.equal((await subir('ana', 'File B.rxdata', partida('de ana'), 0)).status, 200);
  assert.equal((await pedir('/api/archivos/File%20B.rxdata', { usuario: 'beto' })).status, 404);
  const lista = await (await pedir('/api/archivos', { usuario: 'beto' })).json();
  assert.ok(!lista.archivos.some((a) => a.nombre === 'File B.rxdata'));
  const propio = await pedir('/api/archivos/File%20B.rxdata', { usuario: 'ana' });
  assert.equal(propio.status, 200);
  assert.equal(Buffer.from(await propio.arrayBuffer()).toString('latin1').slice(2), 'de ana');
  assert.equal((await pedir('/api/archivos', {})).status, 401);
});

test('una versión vieja da 409', async () => {
  assert.equal((await subir('beto', 'File C.rxdata', partida('1'), 0)).status, 200);
  assert.equal((await subir('beto', 'File C.rxdata', partida('2'), 1)).status, 200);
  const r = await subir('beto', 'File C.rxdata', partida('vieja'), 1);
  assert.equal(r.status, 409);
  assert.equal((await r.json()).version, 2);
  assert.equal((await pedir('/api/archivos/File%20C.rxdata', { method: 'PUT', usuario: 'beto', body: partida('x') })).status, 428);
});

test('se rechazan .rxdata sin 04 08, nombres fuera de la lista y ..', async () => {
  assert.equal((await subir('ana', 'File D.rxdata', Buffer.from('hola'), 0)).status, 400);
  assert.equal((await subir('ana', 'File AA.rxdata', partida('x'), 0)).status, 400);
  assert.equal((await subir('ana', 'otro.txt', partida('x'), 0)).status, 400);
  assert.equal((await subir('ana', '../beto/File A.rxdata', partida('x'), 0)).status, 400);
  assert.equal((await pedir('/api/archivos/..%2Fbeto%2FFile%20C.rxdata', { usuario: 'ana' })).status, 400);
  assert.equal((await subir('ana', 'keybindings.mkxp1', Buffer.from('teclas'), 0)).status, 200);
});

test('guarda solo las últimas 10 versiones', async () => {
  for (let v = 0; v < 12; v++) assert.equal((await subir('ana', 'File A.rxdata', partida(`v${v + 1}`), v)).status, 200);
  const enDisco = (await readdir(path.join(datos, 'ana', 'File A.rxdata'))).map(Number).sort((a, b) => a - b);
  assert.deepEqual(enDisco, [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
  const r = await pedir('/api/archivos/File%20A.rxdata', { usuario: 'ana' });
  assert.equal(r.headers.get('etag'), '"12"');
  assert.equal(Buffer.from(await r.arrayBuffer()).toString('latin1').slice(2), 'v12');
  const lista = (await (await pedir('/api/archivos', { usuario: 'ana' })).json()).archivos;
  assert.deepEqual(lista.find((a) => a.nombre === 'File A.rxdata'), { nombre: 'File A.rxdata', version: 12, bytes: 5 });
});

test('/api/fallo guarda la línea con el usuario de la sesión y limita a 10 por hora', async () => {
  const reporte = (n) => pedir('/api/fallo', { method: 'POST', usuario: 'beto', body: JSON.stringify({ usuario: 'falso', n }) });
  assert.equal((await pedir('/api/fallo', { method: 'POST', usuario: 'ana', body: JSON.stringify({ x: 'a'.repeat(70000) }) })).status, 413);
  for (let n = 0; n < 10; n++) assert.equal((await reporte(n)).status, 204);
  assert.equal((await reporte(10)).status, 429);
  const lineas = (await readFile(path.join(datos, 'fallos.jsonl'), 'utf8')).trim().split('\n').map((l) => JSON.parse(l));
  const deBeto = lineas.filter((l) => l.usuario === 'beto');
  assert.equal(deBeto.length, 10);
  assert.equal(deBeto[0].reporte.usuario, 'falso'); // queda dentro del reporte, no reemplaza al real
});

test('el SSE recibe la posición de otro; la inválida se descarta y el nombre sale de la sesión', async () => {
  const corte = new AbortController();
  const stream = await pedir('/api/red', { usuario: 'beto', signal: corte.signal });
  assert.equal(stream.status, 200);
  assert.match(stream.headers.get('content-type'), /^text\/event-stream/);
  const enviar = (pos) => pedir('/api/red', { method: 'POST', usuario: 'ana', body: JSON.stringify(pos) });
  assert.equal((await enviar({ map_id: 5, x: 10000, y: 3, dir: 2, gender: 'f' })).status, 400);
  assert.equal((await enviar({ map_id: 5, x: 1.5, y: 3, dir: 2 })).status, 400);
  assert.equal((await enviar({ map_id: 5, x: 7, y: 3, dir: 4, gender: 'f', nombre: 'Impostor', id: 'beto' })).status, 204);

  const lector = stream.body.getReader();
  let texto = '';
  const limite = setTimeout(() => corte.abort(), 3000);
  while (!texto.includes('data: ')) {
    const { value, done } = await lector.read();
    if (done) break;
    texto += new TextDecoder().decode(value);
  }
  while (!texto.includes('\n\n', texto.indexOf('data: '))) texto += new TextDecoder().decode((await lector.read()).value);
  clearTimeout(limite);
  corte.abort();
  const eventos = texto.split('\n').filter((l) => l.startsWith('data: ')).map((l) => JSON.parse(l.slice(6)));
  assert.deepEqual(eventos[0], { id: 'ana', nombre: 'Ana', map_id: 5, x: 7, y: 3, dir: 4, gender: 'f' });
});

const PK = (especie, pid) => `${especie}|25|TACKLE,GROWL||HARDY||31,31,31,31,31,31|0,0,0,0,0,0|0|0|Apodo|${pid}`.replace('||HARDY', '|0|HARDY');
const json = (cuerpo) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) });

test('el equipo se guarda solo si cada línea es válida y otro jugador lo puede leer', async () => {
  const subirEquipo = (cuerpo) => pedir('/api/equipo', { method: 'PUT', usuario: 'ana', body: cuerpo });
  assert.equal((await subirEquipo(PK('B1H4', 1) + '\n' + PK('PIKACHU', 2).replace('|25|', '|101|'))).status, 400);
  assert.equal((await subirEquipo(PK('PIKACHU', 2).replace('Apodo', 'a|b'))).status, 400);
  assert.equal((await subirEquipo('x'.repeat(5000))).status, 413);
  assert.equal((await subirEquipo([PK('B1H4', 1), PK('PIKACHU', 2)].join('\n'))).status, 204);
  const r = await pedir('/api/equipo/ana', { usuario: 'beto' });
  assert.deepEqual(await r.json(), { uid: 'ana', nombre: 'Ana', lineas: [PK('B1H4', 1), PK('PIKACHU', 2)] });
  assert.equal((await pedir('/api/equipo/..%2Fana', { usuario: 'beto' })).status, 400);
  const amigos = await (await pedir('/api/amigos', { usuario: 'beto' })).json();
  assert.deepEqual(amigos.amigos.map((a) => a.uid), ['ana']);
});

test('intercambio: no con uno mismo, aceptar una vez y se borra cuando ambos lo reciben', async () => {
  assert.equal((await pedir('/api/intercambio', { usuario: 'ana', ...json({ para: 'ana', pokemon: PK('PIKACHU', 2) }) })).status, 400);
  assert.equal((await pedir('/api/intercambio', { usuario: 'ana', ...json({ para: 'beto', pokemon: 'malo' }) })).status, 400);
  const { id } = await (await pedir('/api/intercambio', { usuario: 'ana', ...json({ para: 'beto', pokemon: PK('PIKACHU', 2) }) })).json();
  const deBeto = await (await pedir('/api/intercambio', { usuario: 'beto' })).json();
  assert.equal(deBeto.intercambios[0].rol, 'para');
  assert.equal(deBeto.intercambios[0].pokemonDe, PK('PIKACHU', 2));

  const aceptar = (usuario) => pedir(`/api/intercambio/${id}/aceptar`, { usuario, ...json({ pokemon: PK('EEVEE', 3) }) });
  assert.equal((await aceptar('ana')).status, 409); // quien ofrece no acepta
  assert.equal((await aceptar('beto')).status, 200);
  assert.equal((await aceptar('beto')).status, 409); // aceptar dos veces no duplica
  const recibido = (usuario) => pedir(`/api/intercambio/${id}/recibido`, { usuario, method: 'POST' });
  assert.equal((await recibido('ana')).status, 200);
  assert.equal((await recibido('ana')).status, 200);
  const deAna = await (await pedir('/api/intercambio', { usuario: 'ana' })).json();
  assert.equal(deAna.intercambios.length, 0); // ana ya lo aplicó
  assert.equal((await recibido('beto')).status, 200);
  assert.equal((await recibido('beto')).status, 404); // borrado: ambos lo aplicaron
});

test('el chat llega a todos con el nombre de la sesión y tiene límite', async () => {
  const corte = new AbortController();
  const stream = await pedir('/api/red', { usuario: 'beto', signal: corte.signal });
  assert.equal((await pedir('/api/chat', { usuario: 'ana', ...json({ texto: '' }) })).status, 400);
  await new Promise((ok) => setTimeout(ok, 1100));
  assert.equal((await pedir('/api/chat', { usuario: 'ana', ...json({ texto: 'hola\nbeto', nombre: 'Falso' }) })).status, 204);
  assert.equal((await pedir('/api/chat', { usuario: 'ana', ...json({ texto: 'otra' }) })).status, 429);
  const lector = stream.body.getReader();
  let texto = '';
  const limite = setTimeout(() => corte.abort(), 3000);
  while (!/"tipo":"chat"[^\n]*\n\n/.test(texto)) {
    const { value, done } = await lector.read();
    if (done) break;
    texto += new TextDecoder().decode(value);
  }
  clearTimeout(limite);
  corte.abort();
  const chat = texto.split('\n').filter((l) => l.startsWith('data: ')).map((l) => JSON.parse(l.slice(6))).find((e) => e.tipo === 'chat');
  assert.equal(chat.nombre, 'Ana');
  assert.equal(chat.texto, 'hola beto');
});

test('un Pokémon no entra en dos intercambios abiertos ni lleva códigos de control', async () => {
  assert.equal(limpiarPokemon(PK('PIKACHU', 9).replace('Apodo', String.raw`a\c[2]b`)), null);
  assert.equal(limpiarPokemon(PK('PIKACHU', 9).replace('Apodo', '<ac>hola')), null);
  const ofrecer = () => pedir('/api/intercambio', { usuario: 'ana', ...json({ para: 'beto', pokemon: PK('MEW', 77) }) });
  assert.equal((await ofrecer()).status, 201);
  assert.equal((await ofrecer()).status, 409); // el mismo personalID ya está ofrecido
  const { intercambios } = await (await pedir('/api/intercambio', { usuario: 'beto' })).json();
  const { id } = intercambios.find((t) => t.pokemonDe === PK('MEW', 77));
  assert.equal((await pedir(`/api/intercambio/${id}/rechazar`, { method: 'POST', usuario: 'beto' })).status, 200);
  assert.equal((await ofrecer()).status, 201); // rechazado: vuelve a estar libre
});
