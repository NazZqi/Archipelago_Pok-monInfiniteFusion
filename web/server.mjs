// Servidor de PIF en el navegador: login con Nextcloud, juego tras sesión, archivos del jugador,
// reportes de fallos y posiciones de los demás jugadores. Sin dependencias (Node 22).
import http from 'node:http';
import { readFile, writeFile, appendFile, rename, rm, mkdir, readdir, stat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { pipeline } from 'node:stream/promises';
import { randomBytes, randomUUID } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = path.dirname(fileURLToPath(import.meta.url));
const TIPOS = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.webmanifest': 'application/manifest+json',
  '.wasm': 'application/wasm', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
};
// SharedArrayBuffer del core exige aislamiento entre orígenes en la página y en todo lo que carga.
const CABECERAS = {
  'Cross-Origin-Opener-Policy': 'same-origin',
  'Cross-Origin-Embedder-Policy': 'require-corp',
  'X-Content-Type-Options': 'nosniff',
};
const COOKIE = 'pif_sesion';
const DURACION_SESION = 7 * 24 * 3600e3; // una cuenta desactivada en Nextcloud pierde acceso a más tardar en este plazo
const MAX_ARCHIVO = 20 * 1024 * 1024;
const MAX_VERSIONES = 10;
const MAX_FALLO = 64 * 1024;
const MAX_FALLOS_ARCHIVO = 10 * 1024 * 1024;
const VIGENCIA_POSICION = 30e3;
const LATIDO = 25e3; // Cloudflare corta a los 100 s sin tráfico
const MAX_STREAMS = 4; // conexiones SSE por usuario

// Nombres que PIF escribe en System.data_directory. Nada con rutas: la lista blanca excluye "/" y "..".
export const nombreValido = (n) => /^File [A-Z]\.rxdata$/.test(n) || n === 'keybindings.mkxp1';
// El uid es carpeta en disco: solo caracteres seguros, sin empezar con punto ni chocar con fallos.jsonl.
export const uidValido = (u) => typeof u === 'string' && /^[A-Za-z0-9_@-][A-Za-z0-9._@-]{0,63}$/.test(u) && !u.startsWith('fallos.jsonl');

// Igual que clean_position de client.py, salvo que no convierte: solo acepta enteros JSON.
export function limpiarPosicion(b) {
  const pos = {};
  for (const k of ['map_id', 'x', 'y', 'dir']) {
    if (!Number.isInteger(b?.[k])) return null;
    pos[k] = b[k];
  }
  if (![2, 4, 6, 8].includes(pos.dir) || !['map_id', 'x', 'y'].every((k) => pos[k] >= 0 && pos[k] < 10000)) return null;
  pos.gender = b.gender === 'f' ? 'f' : 'm'; // como client.py: un género inválido pasa a "m"
  return pos;
}

// Un Pokémon viaja como una línea de texto (web_equipo.rb), nunca como Marshal: el juego que la
// recibe la vuelve a validar contra GameData. Aquí solo se revisa la forma.
// especie|nivel|movs|habilidad|naturaleza|objeto|ivs|evs|shiny|género|apodo|personalID
const SIMBOLO = /^[A-Z0-9_]{1,40}$/;
const enteros = (t, n, max) => {
  const v = t.split(',').map(Number);
  return v.length === n && v.every((x) => Number.isInteger(x) && x >= 0 && x <= max) ? v : null;
};
export function limpiarPokemon(linea) {
  if (typeof linea !== 'string' || linea.length > 300 || /[\t\r\n]/.test(linea)) return null;
  const c = linea.split('|');
  if (c.length !== 12) return null;
  const [especie, nivel, movs, habilidad, naturaleza, objeto, ivs, evs, shiny, genero, apodo, pid] = c;
  const movimientos = movs ? movs.split(',') : [];
  const evsV = enteros(evs, 6, 252);
  const ok = SIMBOLO.test(especie) && /^(100|[1-9]\d?)$/.test(nivel)
    && movimientos.length <= 4 && movimientos.every((m) => SIMBOLO.test(m))
    && /^[0-2]$/.test(habilidad) && (naturaleza === '' || SIMBOLO.test(naturaleza))
    && (objeto === '' || SIMBOLO.test(objeto)) && enteros(ivs, 6, 31) && evsV
    && evsV.reduce((a, b) => a + b, 0) <= 510 && /^[01]$/.test(shiny) && /^[0-2]$/.test(genero)
    && [...apodo].length <= 20 && !/[\\<>\u0000-\u001f\u007f]/.test(apodo) && /^\d{1,10}$/.test(pid);
  return ok ? linea : null;
}

const fallo = (estado, mensaje, extra) => Object.assign(new Error(mensaje), { estado, extra });

export function crearServidor({
  nextcloud, // URL base, p. ej. https://nube.cinderlink.cl
  datos = '/mnt/datos/pif',
  juego,
  publico = path.join(RAIZ, 'public'),
  origen, // origen permitido en escrituras; sin él se compara con Host
  cabeceraIp, // cabecera con la IP real tras el proxy, p. ej. cf-connecting-ip
} = {}) {
  if (!nextcloud) throw new Error('Falta la URL de Nextcloud');
  if (!juego) throw new Error('Falta la carpeta del juego');
  const urlUsuario = nextcloud.replace(/\/+$/, '') + '/ocs/v2.php/cloud/user?format=json';
  const archivoFallos = path.join(datos, 'fallos.jsonl');

  // shortcut: sesiones en memoria, reiniciar el servidor obliga a entrar de nuevo; pasar a disco si molesta.
  const sesiones = new Map(); // token → { uid, nombre, expira }
  const posiciones = new Map(); // uid → { id, nombre, map_id, x, y, dir, gender, t }
  const streams = new Map(); // uid → Set de respuestas SSE
  const intentosLogin = new Map(), envioFallos = new Map(), envioRed = new Map(), envioChat = new Map();
  const limites = [[intentosLogin, 15 * 60e3], [envioFallos, 3600e3], [envioRed, 1000], [envioChat, 1000]];
  // Un uid no puede empezar con punto: esta carpeta no choca con ningún usuario
  const carpetaIntercambios = path.join(datos, '.intercambios');
  const colas = new Map(); // serializa escrituras por clave

  const enCola = (clave, fn) => {
    const p = (colas.get(clave) ?? Promise.resolve()).then(fn);
    colas.set(clave, p.catch(() => {}));
    return p;
  };
  // Ventana deslizante: true si la clave ya gastó sus `max` usos en `ms`.
  const excede = (mapa, clave, max, ms) => {
    const ahora = Date.now();
    const usos = (mapa.get(clave) || []).filter((t) => t > ahora - ms);
    const lleno = usos.length >= max;
    if (!lleno) usos.push(ahora);
    mapa.set(clave, usos);
    return lleno;
  };

  const json = (res, code, obj, extra = {}) => {
    res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...extra });
    res.end(JSON.stringify(obj));
  };
  const ipDe = (req) => (cabeceraIp && String(req.headers[cabeceraIp.toLowerCase()] || '').split(',')[0].trim()) || req.socket.remoteAddress;
  const origenValido = (req) => {
    const o = req.headers.origin;
    if (!o) return false;
    if (origen) return o === origen;
    try { return new URL(o).host === req.headers.host; } catch { return false; }
  };
  const sesionDe = (req) => {
    const m = new RegExp(`(?:^|;\\s*)${COOKIE}=([A-Za-z0-9_-]+)`).exec(req.headers.cookie || '');
    const s = m && sesiones.get(m[1]);
    return s && s.expira > Date.now() ? s : null;
  };
  const leerCuerpo = (req, max) => new Promise((ok, mal) => {
    if (Number(req.headers['content-length']) > max) return mal(fallo(413, 'Demasiado grande'));
    let n = 0; const partes = [];
    req.on('data', (c) => { n += c.length; if (n > max) { mal(fallo(413, 'Demasiado grande')); req.destroy(); } else partes.push(c); });
    req.on('end', () => ok(Buffer.concat(partes)));
    req.on('error', mal);
  });
  const leerJson = async (req, max) => {
    let b;
    try { b = JSON.parse((await leerCuerpo(req, max)).toString()); } catch (e) { throw e.estado ? e : fallo(400, 'JSON inválido'); }
    if (!b || typeof b !== 'object' || Array.isArray(b)) throw fallo(400, 'Se esperaba un objeto');
    return b;
  };
  const versiones = async (dir) => {
    try { return (await readdir(dir)).filter((n) => /^\d+$/.test(n)).map(Number).sort((a, b) => a - b); }
    catch (e) { if (e.code === 'ENOENT') return []; throw e; }
  };
  const emitir = (obj, excepto) => {
    const linea = `data: ${JSON.stringify(obj)}\n\n`;
    for (const [uid, set] of streams) if (uid !== excepto) for (const r of set) r.write(linea);
  };
  const avisarA = (uid, obj) => { for (const r of streams.get(uid) || []) r.write(`data: ${JSON.stringify(obj)}\n\n`); };
  const escribirAtomico = async (archivo, contenido) => {
    await mkdir(path.dirname(archivo), { recursive: true });
    const tmp = path.join(path.dirname(archivo), `.tmp-${randomUUID()}`);
    await writeFile(tmp, contenido);
    await rename(tmp, archivo);
  };
  const leerJsonArchivo = async (archivo) => {
    try { return JSON.parse(await readFile(archivo, 'utf8')); } catch (e) { if (e.code === 'ENOENT') return null; throw e; }
  };

  async function login(req, res) {
    if (excede(intentosLogin, ipDe(req), 10, 15 * 60e3)) throw fallo(429, 'Demasiados intentos, espera unos minutos');
    const b = await leerJson(req, 4096);
    if (typeof b.usuario !== 'string' || typeof b.clave !== 'string' || !b.usuario || !b.clave
      || b.usuario.includes(':') || b.usuario.length > 256 || b.clave.length > 1024) throw fallo(400, 'Usuario o clave inválidos');
    let r;
    try {
      r = await fetch(urlUsuario, {
        headers: {
          Authorization: 'Basic ' + Buffer.from(`${b.usuario}:${b.clave}`).toString('base64'),
          'OCS-APIRequest': 'true', Accept: 'application/json',
        },
        redirect: 'error', signal: AbortSignal.timeout(10e3),
      });
    } catch { throw fallo(502, 'Nextcloud no responde'); }
    // Nextcloud responde 401 también a cuentas desactivadas, y Registration deja desactivada la cuenta sin aprobar.
    if (r.status === 401) throw fallo(401, 'Usuario o clave incorrectos');
    if (!r.ok) throw fallo(502, 'Nextcloud respondió ' + r.status);
    const d = (await r.json().catch(() => null))?.ocs?.data;
    // Para el propio usuario Nextcloud omite `enabled`: solo se rechaza si viene en false.
    if (!d || d.enabled === false) throw fallo(403, 'Cuenta desactivada o sin aprobar');
    if (!uidValido(d.id)) throw fallo(403, 'Usuario no admitido');
    const token = randomBytes(32).toString('base64url');
    // Sin "\", "<", ">" ni controles: el nombre llega a mensajes del juego (códigos \c[n], etiquetas <c2=…>)
    // y a órdenes separadas por tab
    const nombre = String(d.displayname || d['display-name'] || d.id).replace(/[\\|<>\u0000-\u001f\u007f]/g, '').slice(0, 32) || d.id;
    sesiones.set(token, { uid: d.id, nombre, expira: Date.now() + DURACION_SESION });
    json(res, 200, { uid: d.id, nombre }, {
      'Set-Cookie': `${COOKIE}=${token}; Path=/; Max-Age=${DURACION_SESION / 1000}; HttpOnly; Secure; SameSite=Strict`,
    });
  }

  async function archivos(req, res, s, crudo) {
    const carpeta = path.join(datos, s.uid);
    if (crudo === undefined) {
      if (req.method !== 'GET') throw fallo(405, 'Método no permitido');
      let nombres = [];
      try { nombres = await readdir(carpeta); } catch (e) { if (e.code !== 'ENOENT') throw e; }
      const lista = [];
      for (const nombre of nombres.filter(nombreValido)) {
        const v = (await versiones(path.join(carpeta, nombre))).at(-1);
        if (v) lista.push({ nombre, version: v, bytes: (await stat(path.join(carpeta, nombre, String(v)))).size });
      }
      return json(res, 200, { archivos: lista });
    }
    let nombre;
    try { nombre = decodeURIComponent(crudo); } catch { throw fallo(400, 'Nombre inválido'); }
    if (!nombreValido(nombre)) throw fallo(400, 'Nombre no permitido');
    const dir = path.join(carpeta, nombre); // solo con el uid de la sesión: nunca se llega a otro usuario
    if (req.method === 'GET') {
      const v = (await versiones(dir)).at(-1);
      if (!v) throw fallo(404, 'No existe');
      const contenido = await readFile(path.join(dir, String(v)));
      res.writeHead(200, { 'Content-Type': 'application/octet-stream', 'Cache-Control': 'no-store', ETag: `"${v}"`, 'Content-Length': contenido.length });
      return res.end(contenido);
    }
    if (req.method !== 'PUT') throw fallo(405, 'Método no permitido');
    const m = /^"?(\d+)"?$/.exec(req.headers['if-match'] || '');
    if (!m) throw fallo(428, 'Falta If-Match con la versión (0 si es nuevo)');
    const cuerpo = await leerCuerpo(req, MAX_ARCHIVO);
    // Toda partida Marshal empieza con la versión 4.8.
    if (nombre.endsWith('.rxdata') && !(cuerpo[0] === 0x04 && cuerpo[1] === 0x08)) throw fallo(400, 'No es una partida válida');
    const version = await enCola(s.uid, async () => {
      const vers = await versiones(dir);
      const actual = vers.at(-1) || 0;
      if (Number(m[1]) !== actual) throw fallo(409, 'Hay una versión más nueva', { version: actual });
      await mkdir(dir, { recursive: true });
      const tmp = path.join(dir, `.tmp-${randomUUID()}`);
      await writeFile(tmp, cuerpo);
      await rename(tmp, path.join(dir, String(actual + 1)));
      for (const viejo of vers.slice(0, Math.max(0, vers.length + 1 - MAX_VERSIONES))) await rm(path.join(dir, String(viejo)));
      return actual + 1;
    });
    json(res, 200, { version }, { ETag: `"${version}"` });
  }

  async function reportarFallo(req, res, s) {
    if (excede(envioFallos, s.uid, 10, 3600e3)) throw fallo(429, 'Demasiados reportes, espera una hora');
    const reporte = await leerJson(req, MAX_FALLO);
    // usuario, hora y navegador los pone el servidor: el cliente no los puede falsear.
    const linea = JSON.stringify({ hora: new Date().toISOString(), usuario: s.uid, navegador: req.headers['user-agent'] || '', reporte }) + '\n';
    await enCola('fallos', async () => {
      await mkdir(datos, { recursive: true });
      let tam = 0;
      try { tam = (await stat(archivoFallos)).size; } catch (e) { if (e.code !== 'ENOENT') throw e; }
      if (tam && tam + Buffer.byteLength(linea) > MAX_FALLOS_ARCHIVO) await rename(archivoFallos, archivoFallos + '.1');
      await appendFile(archivoFallos, linea);
    });
    res.writeHead(204); res.end();
  }

  function abrirRed(req, res, s) {
    const set = streams.get(s.uid) || new Set();
    if (set.size >= MAX_STREAMS) throw fallo(429, 'Demasiadas conexiones');
    set.add(res); streams.set(s.uid, set);
    req.on('close', () => { set.delete(res); if (!set.size && streams.get(s.uid) === set) streams.delete(s.uid); });
    res.writeHead(200, { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no' });
    res.write(': hola\n\n');
    const ahora = Date.now();
    for (const [uid, p] of posiciones) if (uid !== s.uid && ahora - p.t < VIGENCIA_POSICION) res.write(`data: ${JSON.stringify({ ...p, t: undefined })}\n\n`);
  }

  async function enviarPosicion(req, res, s) {
    if (excede(envioRed, s.uid, 4, 1000)) throw fallo(429, 'Demasiadas posiciones');
    const pos = limpiarPosicion(await leerJson(req, 1024));
    if (!pos) throw fallo(400, 'Posición inválida');
    const p = { id: s.uid, nombre: s.nombre, ...pos }; // el nombre sale de la sesión, nunca del cliente
    posiciones.set(s.uid, { ...p, t: Date.now() });
    emitir(p, s.uid);
    res.writeHead(204); res.end();
  }

  // Equipo propio, para que los amigos peleen contra él (combate amistoso con la IA del juego)
  async function equipo(req, res, s, crudo) {
    if (crudo === undefined) {
      if (req.method !== 'PUT') throw fallo(405, 'Método no permitido');
      const lineas = (await leerCuerpo(req, 4096)).toString('utf8').split('\n').filter(Boolean);
      if (!lineas.length || lineas.length > 6 || !lineas.every(limpiarPokemon)) throw fallo(400, 'Equipo inválido');
      await enCola(s.uid, () => escribirAtomico(path.join(datos, s.uid, 'equipo.json'), JSON.stringify({ nombre: s.nombre, lineas })));
      res.writeHead(204);
      return res.end();
    }
    if (req.method !== 'GET') throw fallo(405, 'Método no permitido');
    let uid;
    try { uid = decodeURIComponent(crudo); } catch { throw fallo(400, 'Usuario inválido'); }
    if (!uidValido(uid)) throw fallo(400, 'Usuario inválido');
    const e = await leerJsonArchivo(path.join(datos, uid, 'equipo.json'));
    if (!e) throw fallo(404, 'Ese jugador no tiene equipo guardado');
    json(res, 200, { uid, ...e });
  }

  async function amigos(req, res, s) {
    let nombres = [];
    try { nombres = await readdir(datos); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    const lista = [];
    for (const uid of nombres.filter((n) => uidValido(n) && n !== s.uid)) {
      const e = await leerJsonArchivo(path.join(datos, uid, 'equipo.json'));
      if (e) lista.push({ uid, nombre: e.nombre, conectado: posiciones.has(uid) });
    }
    json(res, 200, { amigos: lista });
  }

  // Intercambio en dos pasos: uno ofrece, el otro acepta con el suyo. Cada juego aplica el cambio
  // y avisa "recibido"; el registro se borra cuando ambos lo aplicaron.
  const archivoIntercambio = (id) => path.join(carpetaIntercambios, `${id}.json`);
  const listarIntercambios = async () => {
    let nombres = [];
    try { nombres = await readdir(carpetaIntercambios); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    const lista = [];
    for (const n of nombres.filter((x) => /^[0-9a-f-]{36}\.json$/.test(x))) {
      const t = await leerJsonArchivo(path.join(carpetaIntercambios, n));
      if (t) lista.push(t);
    }
    return lista;
  };

  // Un Pokémon (personalID) solo puede estar en un intercambio abierto: ofrecido a dos amigos
  // que aceptan, ambos lo recibirían
  const pidDe = (linea) => linea?.split('|')[11];
  const ocupado = (lista, uid, pid) => lista.some((t) => (t.de === uid && pidDe(t.pokemonDe) === pid && !t.entregado.de)
    || (t.para === uid && pidDe(t.pokemonPara) === pid && !t.entregado.para));

  async function intercambios(req, res, s, id, accion) {
    if (id === undefined) {
      if (req.method === 'GET') {
        const mios = (await listarIntercambios()).filter((t) => {
          const rol = t.de === s.uid ? 'de' : t.para === s.uid ? 'para' : null;
          return rol && !(t.estado === 'aceptado' && t.entregado[rol]);
        });
        return json(res, 200, { intercambios: mios.map((t) => ({ ...t, rol: t.de === s.uid ? 'de' : 'para' })) });
      }
      if (req.method !== 'POST') throw fallo(405, 'Método no permitido');
      const b = await leerJson(req, 2048);
      if (!uidValido(b.para) || b.para === s.uid) throw fallo(400, 'Destinatario inválido');
      const pokemon = limpiarPokemon(b.pokemon);
      if (!pokemon) throw fallo(400, 'Pokémon inválido');
      const t = { id: randomUUID(), de: s.uid, nombreDe: s.nombre, para: b.para, pokemonDe: pokemon,
                  pokemonPara: null, estado: 'ofrecido', entregado: { de: false, para: false }, creado: Date.now() };
      await enCola('intercambios', async () => {
        const lista = await listarIntercambios();
        if (lista.filter((x) => x.de === s.uid && x.estado === 'ofrecido').length >= 5) throw fallo(429, 'Ya tienes 5 ofertas sin responder');
        if (ocupado(lista, s.uid, pidDe(pokemon))) throw fallo(409, 'Ese Pokémon ya está en otro intercambio');
        await escribirAtomico(archivoIntercambio(t.id), JSON.stringify(t));
      });
      avisarA(b.para, { tipo: 'intercambio' });
      return json(res, 201, { id: t.id });
    }
    if (!/^[0-9a-f-]{36}$/.test(id)) throw fallo(404, 'No existe');
    if (req.method !== 'POST') throw fallo(405, 'Método no permitido');
    const cuerpo = accion === 'aceptar' ? await leerJson(req, 2048) : null;
    const t = await enCola('intercambios', async () => {
      const t = await leerJsonArchivo(archivoIntercambio(id));
      if (!t || (t.de !== s.uid && t.para !== s.uid)) throw fallo(404, 'No existe');
      const rol = t.de === s.uid ? 'de' : 'para';
      if (accion === 'aceptar') {
        if (rol !== 'para' || t.estado !== 'ofrecido') throw fallo(409, 'Ya no está disponible');
        const pokemon = limpiarPokemon(cuerpo.pokemon);
        if (!pokemon) throw fallo(400, 'Pokémon inválido');
        if (ocupado(await listarIntercambios(), s.uid, pidDe(pokemon))) throw fallo(409, 'Ese Pokémon ya está en otro intercambio');
        t.pokemonPara = pokemon;
        t.estado = 'aceptado';
      } else if (accion === 'rechazar') {
        if (t.estado !== 'ofrecido') throw fallo(409, 'Ya no está disponible');
        await rm(archivoIntercambio(id));
        return { ...t, estado: 'rechazado' };
      } else if (accion === 'recibido') {
        if (t.estado !== 'aceptado') throw fallo(409, 'Todavía no se acepta');
        t.entregado[rol] = true;
        if (t.entregado.de && t.entregado.para) {
          await rm(archivoIntercambio(id));
          return t;
        }
      } else throw fallo(404, 'No encontrado');
      await escribirAtomico(archivoIntercambio(id), JSON.stringify(t));
      return t;
    });
    avisarA(t.de === s.uid ? t.para : t.de, { tipo: 'intercambio' });
    json(res, 200, { estado: t.estado });
  }

  async function chat(req, res, s) {
    if (excede(envioChat, s.uid, 1, 1000)) throw fallo(429, 'Espera un segundo entre mensajes');
    const b = await leerJson(req, 2048);
    const texto = typeof b.texto === 'string' ? b.texto.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, 500) : '';
    if (!texto) throw fallo(400, 'Mensaje vacío');
    emitir({ tipo: 'chat', id: s.uid, nombre: s.nombre, texto, hora: Date.now() }); // el nombre sale de la sesión
    res.writeHead(204);
    res.end();
  }

  async function api(req, res, url) {
    const p = url.pathname;
    if (p === '/api/login' && req.method === 'POST') return login(req, res);
    const s = sesionDe(req);
    if (!s) throw fallo(401, 'Sin sesión');
    if (p === '/api/archivos') return archivos(req, res, s);
    const m = /^\/api\/archivos\/([^/]+)$/.exec(p);
    if (m) return archivos(req, res, s, m[1]);
    if (p === '/api/fallo' && req.method === 'POST') return reportarFallo(req, res, s);
    if (p === '/api/red' && req.method === 'GET') return abrirRed(req, res, s);
    if (p === '/api/red' && req.method === 'POST') return enviarPosicion(req, res, s);
    if (p === '/api/equipo') return equipo(req, res, s);
    const e = /^\/api\/equipo\/([^/]+)$/.exec(p);
    if (e) return equipo(req, res, s, e[1]);
    if (p === '/api/amigos' && req.method === 'GET') return amigos(req, res, s);
    if (p === '/api/intercambio') return intercambios(req, res, s);
    const t = /^\/api\/intercambio\/([^/]+)\/(aceptar|rechazar|recibido)$/.exec(p);
    if (t) return intercambios(req, res, s, t[1], t[2]);
    if (p === '/api/chat' && req.method === 'POST') return chat(req, res, s);
    throw fallo(404, 'No encontrado');
  }

  async function estatico(req, res, base, pathname, cache) {
    if (req.method !== 'GET' && req.method !== 'HEAD') throw fallo(405, 'Método no permitido');
    let ruta;
    try { ruta = decodeURIComponent(pathname); } catch { throw fallo(400, 'Ruta inválida'); }
    if (ruta.includes('\0')) throw fallo(400, 'Ruta inválida');
    if (ruta.endsWith('/')) ruta += 'index.html';
    const raiz = path.resolve(base);
    const archivo = path.join(raiz, ruta);
    if (!archivo.startsWith(raiz + path.sep)) throw fallo(403, 'Prohibido');
    let st;
    try { st = await stat(archivo); } catch { st = null; }
    if (!st?.isFile()) throw fallo(404, 'No encontrado');
    // Un solo rango (bytes=a-b, a-, -n); otra forma se ignora y va el archivo entero.
    let ini = 0, fin = st.size - 1, code = 200;
    const r = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || '');
    if (r && (r[1] || r[2])) {
      if (r[1]) { ini = Number(r[1]); if (r[2]) fin = Math.min(Number(r[2]), st.size - 1); }
      else ini = Math.max(0, st.size - Number(r[2]));
      if (ini > fin || ini >= st.size) {
        res.writeHead(416, { 'Content-Range': `bytes */${st.size}` });
        return res.end();
      }
      code = 206;
    }
    res.writeHead(code, {
      'Content-Type': TIPOS[path.extname(archivo)] || 'application/octet-stream',
      'Content-Length': fin - ini + 1,
      'Accept-Ranges': 'bytes',
      'Last-Modified': st.mtime.toUTCString(),
      'Cache-Control': cache,
      ...(code === 206 && { 'Content-Range': `bytes ${ini}-${fin}/${st.size}` }),
    });
    if (req.method === 'HEAD' || fin < ini) return res.end();
    await pipeline(createReadStream(archivo, { start: ini, end: fin }), res);
  }

  const servidor = http.createServer(async (req, res) => {
    for (const [k, v] of Object.entries(CABECERAS)) res.setHeader(k, v);
    try {
      const url = new URL(req.url, 'http://x');
      if (req.method !== 'GET' && req.method !== 'HEAD' && !origenValido(req)) throw fallo(403, 'Origen no permitido');
      if (url.pathname.startsWith('/api/')) await api(req, res, url);
      else if (url.pathname.startsWith('/juego/')) {
        if (!sesionDe(req)) throw fallo(401, 'Sin sesión');
        // private y no-cache: Cloudflare no lo guarda y el navegador no usa un launcher viejo.
        await estatico(req, res, juego, url.pathname.slice('/juego'.length), 'private, no-cache');
      } else await estatico(req, res, publico, url.pathname, 'no-cache');
    } catch (e) {
      if (!e.estado) console.error(e);
      if (res.headersSent) return res.destroyed || res.end();
      json(res, e.estado || 500, { error: e.estado ? e.message : 'Error interno', ...e.extra },
        e.estado === 413 ? { Connection: 'close' } : {});
    }
  });

  const barrido = setInterval(() => {
    const ahora = Date.now();
    for (const [uid, p] of posiciones) if (ahora - p.t >= VIGENCIA_POSICION) { posiciones.delete(uid); emitir({ id: uid, fuera: true }); }
    for (const [t, s] of sesiones) if (s.expira <= ahora) sesiones.delete(t);
    for (const [mapa, ms] of limites) for (const [k, usos] of mapa) if (!usos.some((t) => t > ahora - ms)) mapa.delete(k);
  }, 5e3).unref();
  const latido = setInterval(() => { for (const set of streams.values()) for (const r of set) r.write(': latido\n\n'); }, LATIDO).unref();
  servidor.on('close', () => { clearInterval(barrido); clearInterval(latido); });
  return servidor;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { NEXTCLOUD_URL, PIF_DATOS, PIF_JUEGO, ORIGEN, CABECERA_IP, PORT, HOST } = process.env;
  if (!NEXTCLOUD_URL || !PIF_JUEGO) {
    console.error('Faltan NEXTCLOUD_URL y/o PIF_JUEGO.');
    process.exit(1);
  }
  if (!ORIGEN) console.warn('ORIGEN no definido: las escrituras se aceptan si Origin coincide con Host.');
  const puerto = Number(PORT) || 3301;
  crearServidor({ nextcloud: NEXTCLOUD_URL, datos: PIF_DATOS || '/mnt/datos/pif', juego: PIF_JUEGO, origen: ORIGEN, cabeceraIp: CABECERA_IP })
    .listen(puerto, HOST || '127.0.0.1', () => console.log(`PIF web en :${puerto}`));
}
