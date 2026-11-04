// Une el juego con web/server.mjs. empaquetar.py lo antepone al launcher, y su await detiene el
// arranque hasta tener los archivos del jugador. Sin servidor (prueba local) no hace nada.
// - Baja las partidas y las teclas antes de arrancar, y sube lo que el juego cambia.
// - Avisa al servidor los fallos del core, de Ruby y de WebGL.
// - Retransmite posiciones para los jugadores visibles (web_red.rb).
await (async () => {
  const lista = await fetch('/api/archivos', { cache: 'no-store' }).catch(() => null);
  if (lista?.status === 401) {
    location.href = '/';
    await new Promise(() => {});  // no arrancar mientras se va a la página de entrada
  }
  if (!lista?.ok) return;

  // System.data_directory del juego dentro de OPFS (OPFS_MOUNT del launcher)
  const RUTA = ['saves', 'mkxp-z', 'mkxp-z', 'mkxp-z', 'Saves', 'infinitefusion-'];
  const SINCRONIZADOS = /^File [A-Z]\.rxdata$|^keybindings\.mkxp1$/;  // server.mjs: nombreValido
  const QUIETO_MS = 2000;  // no subir un archivo que el juego sigue escribiendo
  let carpeta = await navigator.storage.getDirectory();
  for (const nombre of RUTA) carpeta = await carpeta.getDirectoryHandle(nombre, { create: true });

  const aviso = document.createElement('div');
  aviso.style.cssText = 'position:fixed;right:8px;bottom:8px;z-index:9;padding:4px 8px;border-radius:4px;'
    + 'font:12px system-ui,sans-serif;color:#fff;background:#0009;pointer-events:none';
  const avisar = (texto) => { aviso.textContent = texto; document.body?.append(aviso); };

  // Estado de la última sincronización, por usuario: en un PC compartido, otra cuenta no ve
  // las partidas de la anterior
  const uid = localStorage.getItem('pif-uid') || '';
  let estado = JSON.parse(localStorage.getItem('pif-sync') || 'null');
  const archivoDe = async (nombre) => (await carpeta.getFileHandle(nombre)).getFile();
  const locales = async () => {
    const mapa = new Map();
    for await (const [nombre, asa] of carpeta.entries()) {
      if (asa.kind === 'file' && SINCRONIZADOS.test(nombre)) mapa.set(nombre, await asa.getFile());
    }
    return mapa;
  };
  if (estado?.uid !== uid) {
    for (const nombre of (await locales()).keys()) await carpeta.removeEntry(nombre);
    estado = { uid, archivos: {} };
  }
  const guardarEstado = () => localStorage.setItem('pif-sync', JSON.stringify(estado));
  const escribir = async (nombre, datos) => {
    const w = await (await carpeta.getFileHandle(nombre, { create: true })).createWritable();
    await w.write(datos);
    await w.close();
  };

  // Lo local gana solo si cambió desde la última subida y el servidor sigue en esa versión:
  // así no se pierde lo que se jugó sin conexión. Si ambos cambiaron, gana el servidor y la
  // copia local queda aparte, fuera de lo que lee el juego.
  const delServidor = new Map((await lista.json()).archivos.map((a) => [a.nombre, a.version]));
  const enDisco = await locales();
  for (const [nombre, version] of delServidor) {
    const previo = estado.archivos[nombre];
    const local = enDisco.get(nombre);
    const cambioLocal = local && local.lastModified !== previo?.lastModified;
    if (cambioLocal && previo?.version === version) continue;  // se sube en la primera revisión
    if (cambioLocal) await escribir(`${nombre}.conflicto-${Date.now()}`, local);
    const r = await fetch(`/api/archivos/${encodeURIComponent(nombre)}`, { cache: 'no-store' });
    if (!r.ok) throw new Error(`no se pudo bajar ${nombre}: HTTP ${r.status}`);
    await escribir(nombre, await r.arrayBuffer());
    estado.archivos[nombre] = { version, lastModified: (await archivoDe(nombre)).lastModified };
  }
  guardarEstado();

  let revisando = false;
  let detenido = false;
  const revisar = async () => {
    if (revisando || detenido) return;
    revisando = true;
    try {
      for (const [nombre, archivo] of await locales()) {
        const previo = estado.archivos[nombre];
        if (archivo.lastModified === previo?.lastModified || Date.now() - archivo.lastModified < QUIETO_MS) continue;
        const r = await fetch(`/api/archivos/${encodeURIComponent(nombre)}`, {
          method: 'PUT', headers: { 'If-Match': String(previo?.version || 0) }, body: archivo,
        });
        if (r.status === 409) {
          detenido = true;
          avisar('Se guardó desde otra pestaña o equipo: recarga para seguir');
          return;
        }
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        estado.archivos[nombre] = { version: (await r.json()).version, lastModified: archivo.lastModified };
        guardarEstado();
        avisar(`Guardado en la nube ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`);
      }
      await revisarErrores();
    } catch (e) {
      console.error('[juego] sincronización', e);
      avisar('Sin conexión, reintentando');
    } finally {
      revisando = false;
    }
  };
  setInterval(revisar, 5000);
  document.addEventListener('visibilitychange', () => document.hidden && revisar());

  // Fallos: consola reciente del core, navegador, GPU y memoria
  const consola = [];
  let reportados = 0;
  const gpu = (() => {
    try {
      const gl = document.createElement('canvas').getContext('webgl2');
      return gl.getParameter(gl.getExtension('WEBGL_debug_renderer_info').UNMASKED_RENDERER_WEBGL);
    } catch { return 'desconocida'; }
  })();
  const reportar = (tipo, mensaje, grave) => {
    if (grave) avisar('Algo falló. Recarga la página; tu última partida guardada está en la nube.');
    if (++reportados > 5) return;
    fetch('/api/fallo', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, keepalive: true,
      body: JSON.stringify({ tipo, mensaje: String(mensaje).slice(0, 4000), gpu,
                             memoria: navigator.deviceMemory, consola: consola.join('\n').slice(-50000) }),
    }).catch(() => {});
  };
  window.__registrarConsola = (texto) => {
    consola.push(texto);
    if (consola.length > 200) consola.shift();
    if (/Aborted|Sandbox trap|\[FATAL\]/.test(texto)) reportar('core', texto, true);
  };
  window.addEventListener('error', (e) => {
    // coi-serviceworker del launcher lanza esto a propósito para recargar una vez
    if (!/coi-serviceworker/.test(e.message)) reportar('js', `${e.message} ${e.filename}:${e.lineno}`);
  });
  window.addEventListener('unhandledrejection', (e) => reportar('js', e.reason?.stack || e.reason));
  document.addEventListener('webglcontextlost', () => reportar('webgl', 'contexto WebGL perdido', true), true);
  // PIF anota sus excepciones de Ruby en errorlog.txt
  let errorlog = null;
  const revisarErrores = async () => {
    const archivo = await archivoDe('errorlog.txt').catch(() => null);
    if (!archivo) return;
    if (errorlog !== null && archivo.lastModified !== errorlog) reportar('ruby', (await archivo.text()).slice(-4000));
    errorlog = archivo.lastModified;
  };

  // Jugadores visibles: posiciones de los demás a red_entrada.txt, la propia desde red_salida.txt
  const otros = new Map();
  let pendiente = null;
  const escribirEntrada = () => {
    pendiente ??= setTimeout(() => {
      pendiente = null;
      const limpio = (t) => String(t).replace(/[\t\r\n]/g, ' ');
      const lineas = [...otros.values()].map((p) =>
        [p.id, p.map_id, p.x, p.y, p.dir, p.gender, p.nombre].map(limpio).join('\t'));
      escribir('red_entrada.txt', lineas.join('\n')).catch((e) => console.error('[juego] red', e));
    }, 300);
  };
  new EventSource('/api/red').onmessage = (e) => {
    const p = JSON.parse(e.data);
    if (p.fuera) otros.delete(p.id); else otros.set(p.id, p);
    escribirEntrada();
  };
  let salida = 0;
  setInterval(async () => {
    const archivo = await archivoDe('red_salida.txt').catch(() => null);
    if (!archivo || archivo.lastModified === salida) return;
    salida = archivo.lastModified;
    const [map_id, x, y, dir, gender] = (await archivo.text()).split(' ');
    fetch('/api/red', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ map_id: +map_id, x: +x, y: +y, dir: +dir, gender }) }).catch(() => {});
  }, 300);
})().catch((e) => {
  document.body.textContent = `No se pudo preparar tu partida (${e.message}). Recarga la página.`;
  throw e;
});
