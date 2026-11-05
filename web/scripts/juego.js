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
    if (p.tipo === 'chat') return panel.chat(p);
    if (p.tipo === 'intercambio') return panel.intercambios();
    if (p.fuera) otros.delete(p.id); else otros.set(p.id, p);
    escribirEntrada();
  };
  // Archivos que escribe Ruby: la página los lee pero nunca los borra (ver web_equipo.rb)
  const alCambiar = async (nombre, accion, ignorarActual = false) => {
    let visto = ignorarActual ? (await archivoDe(nombre).catch(() => null))?.lastModified : 0;
    setInterval(async () => {
      const archivo = await archivoDe(nombre).catch(() => null);
      if (!archivo || archivo.lastModified === visto) return;
      visto = archivo.lastModified;
      accion(await archivo.text());
    }, 300);
  };
  const enviar = (ruta, cuerpo, metodo = 'POST') => fetch(ruta, {
    method: metodo, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo),
  });
  alCambiar('red_salida.txt', (texto) => {
    const [map_id, x, y, dir, gender] = texto.split(' ');
    enviar('/api/red', { map_id: +map_id, x: +x, y: +y, dir: +dir, gender }).catch(() => {});
  });
  // web_equipo.rb lo escribe al guardar: es lo que ven los amigos en un combate amistoso
  alCambiar('red_equipo.txt', (texto) => {
    if (texto) fetch('/api/equipo', { method: 'PUT', body: texto }).catch(() => {});
  });

  // Órdenes al juego (web_equipo.rb), una a la vez: la siguiente sale cuando Ruby responde
  const ordenes = [];
  const enCurso = new Set();  // ids de intercambio que ya están en la cola
  // Los campos van separados por tab: ninguno puede traer uno, ni saltos de línea
  const ordenar = (...campos) => ordenes.push(campos.map((c) => String(c).replace(/[\t\r\n]/g, ' ')).join('\t'));
  let esperando = false;
  alCambiar('red_respuesta.txt', async (texto) => {
    esperando = false;
    const [tipo, a, b] = texto.split('\t');
    const r = await (tipo === 'oferta' ? enviar('/api/intercambio', { para: a, pokemon: b })
      : tipo === 'aceptacion' ? enviar(`/api/intercambio/${a}/aceptar`, { pokemon: b })
        : tipo === 'recibido' ? fetch(`/api/intercambio/${a}/recibido`, { method: 'POST' }) : null)?.catch(() => null);
    if (r && !r.ok && r.status !== 404) panel.aviso((await r.json().catch(() => ({}))).error || `Error ${r.status}`);
    if (tipo === 'error') panel.aviso(`El juego no pudo hacerlo: ${a}`);
    if (tipo === 'recibido') enCurso.delete(a);
    panel.intercambios();
  }, true);
  setInterval(async () => {
    if (esperando || !ordenes.length) return;
    esperando = true;
    await escribir('red_ordenes.txt', ordenes.shift());
  }, 500);

  const panel = (() => {
    const raiz = document.createElement('div');
    raiz.style.cssText = 'position:fixed;left:8px;bottom:8px;z-index:9;font:13px system-ui,sans-serif;color:#fff';
    raiz.innerHTML = `<button data-abrir style="padding:4px 10px;border:0;border-radius:4px;background:#0009;color:#fff;cursor:pointer">Amigos</button>
      <div data-caja hidden style="width:300px;max-height:70vh;overflow:auto;margin-top:6px;padding:8px;border-radius:6px;background:#000c">
        <p data-aviso style="color:#ffb38a;margin:0 0 6px"></p>
        <b>Amigos</b><div data-amigos style="margin:4px 0 8px"></div>
        <b>Intercambios</b><div data-ofertas style="margin:4px 0 8px"></div>
        <b>Chat</b><div data-chat style="height:120px;overflow:auto;margin:4px 0;background:#fff1;padding:4px"></div>
        <input data-texto maxlength="500" placeholder="Escribe y pulsa Enter" style="box-sizing:border-box;width:100%">
      </div>`;
    const $ = (n) => raiz.querySelector(`[data-${n}]`);
    const boton = (texto, accion) => {
      const b = document.createElement('button');
      b.textContent = texto;
      b.style.marginLeft = '4px';
      b.onclick = accion;
      return b;
    };
    const fila = (texto, ...botones) => {
      const d = document.createElement('div');
      d.textContent = texto;
      d.append(...botones);
      return d;
    };
    const describir = (linea) => { const c = linea.split('|'); return `${c[10] || c[0]} Nv. ${c[1]}`; };
    // Las teclas del panel no llegan al juego: este listener se registra antes que el del core.
    // Cortar aquí también impide que lleguen al input, así que el Enter del chat se atiende aquí;
    // el texto se escribe igual, porque eso es la acción por defecto.
    for (const tipo of ['keydown', 'keyup', 'keypress']) {
      window.addEventListener(tipo, (e) => {
        if (!raiz.contains(document.activeElement)) return;
        e.stopImmediatePropagation();
        if (tipo === 'keydown' && e.key === 'Enter' && document.activeElement === $('texto')) mandarChat();
      }, true);
    }

    const amigos = async () => {
      const r = await fetch('/api/amigos', { cache: 'no-store' }).catch(() => null);
      if (!r?.ok) return;
      const lista = (await r.json()).amigos;
      $('amigos').replaceChildren(...(lista.length ? lista.map((a) => fila(`${a.conectado ? '● ' : ''}${a.nombre}`,
        boton('Combatir', async () => {
          const e = await (await fetch(`/api/equipo/${encodeURIComponent(a.uid)}`, { cache: 'no-store' })).json();
          const genero = otros.get(a.uid)?.gender || 'm';
          ordenar('combate', e.nombre, genero, ...e.lineas);
          aviso(`Combate contra ${e.nombre}: empieza cuando estés en el mapa.`);
        }),
        boton('Intercambiar', () => { ordenar('ofrecer', a.uid, a.nombre); aviso('Elige el Pokémon en el juego.'); })))
        : [fila('Aún no hay amigos con equipo guardado. Aparecen al guardar la partida.')]));
    };
    const intercambios = async () => {
      const r = await fetch('/api/intercambio', { cache: 'no-store' }).catch(() => null);
      if (!r?.ok) return;
      const filas = [];
      for (const t of (await r.json()).intercambios) {
        if (t.estado === 'aceptado') {
          if (!enCurso.has(t.id)) {
            enCurso.add(t.id);
            const [sale, llega] = t.rol === 'de' ? [t.pokemonDe, t.pokemonPara] : [t.pokemonPara, t.pokemonDe];
            ordenar('recibir', t.id, sale.split('|')[11], llega);
          }
          filas.push(fila(`Recibiendo ${describir(t.rol === 'de' ? t.pokemonPara : t.pokemonDe)}…`));
        } else if (t.rol === 'para') {
          filas.push(fila(`${t.nombreDe} ofrece ${describir(t.pokemonDe)}`,
            boton('Aceptar', () => ordenar('aceptar', t.id, t.nombreDe, t.pokemonDe)),
            boton('Rechazar', () => fetch(`/api/intercambio/${t.id}/rechazar`, { method: 'POST' }).then(intercambios))));
        } else {
          filas.push(fila(`Ofreciste ${describir(t.pokemonDe)}: esperando respuesta`,
            boton('Cancelar', () => fetch(`/api/intercambio/${t.id}/rechazar`, { method: 'POST' }).then(intercambios))));
        }
      }
      $('ofertas').replaceChildren(...(filas.length ? filas : [fila('Ninguno.')]));
    };
    const aviso = (texto) => { $('aviso').textContent = texto; };
    $('abrir').onclick = () => {
      $('caja').hidden = !$('caja').hidden;
      if (!$('caja').hidden) { amigos(); intercambios(); }
    };
    async function mandarChat() {
      const campo = $('texto');
      if (!campo.value.trim()) return;
      const r = await enviar('/api/chat', { texto: campo.value }).catch(() => null);
      if (r?.ok) campo.value = ''; else aviso((await r?.json().catch(() => ({})))?.error || 'Sin conexión');
    }
    document.body.append(raiz);
    setInterval(() => { if (!$('caja').hidden) amigos(); }, 30000);
    intercambios();  // un intercambio aceptado mientras no jugabas se aplica al entrar
    return {
      aviso, intercambios,
      chat: (m) => {
        const linea = document.createElement('div');
        linea.textContent = `${m.nombre}: ${m.texto}`;
        $('chat').append(linea);
        while ($('chat').children.length > 50) $('chat').firstChild.remove();
        $('chat').scrollTop = 1e9;
        if ($('caja').hidden) $('abrir').textContent = 'Amigos •';
      },
    };
  })();
})().catch((e) => {
  document.body.textContent = `No se pudo preparar tu partida (${e.message}). Recarga la página.`;
  throw e;
});
