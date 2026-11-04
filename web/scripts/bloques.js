// Lee el paquete por bloques con Range y los guarda en OPFS, como Last Havens: la primera
// visita baja solo el arranque, y el resto llega cuando el juego lo pide o en segundo plano.
// empaquetar.py lo antepone al launcher y parchear_core.py lo mete en el core, que lo usa
// desde su hilo de OPFS. Ambos comparten la carpeta de bloques.
var __paqueteRemoto = (() => {
  // 256 KiB: un archivo que falta cuesta un pedido corto (con 1 MiB eran 0,5 s a 20 Mbps)
  const BLOQUE = 1 << 18;
  const EN_MEMORIA = 256;  // 64 MiB en RAM, aparte del heap del juego
  const REINTENTOS = 6;
  const abiertos = new Map();

  const pedir = async (url, ini, fin) => {
    for (let intento = 1; ; intento++) {
      try {
        // Sin no-store, Chrome pone en fila los pedidos a la misma URL por su caché: 6 a la vez
        // tardaban lo mismo que uno tras otro
        const r = await fetch(url, { cache: 'no-store', headers: { Range: `bytes=${ini}-${fin - 1}` } });
        const datos = new Uint8Array(await r.arrayBuffer());
        if (r.status === 206 && datos.length === fin - ini) return datos;
        throw new Error(`HTTP ${r.status}, ${datos.length} de ${fin - ini} bytes`);
      } catch (e) {
        if (intento === REINTENTOS) throw e;
        await new Promise((listo) => setTimeout(listo, 2 ** intento * 250));
      }
    }
  };

  const crear = async (m) => {
    const carpeta = await (await navigator.storage.getDirectory())
      .getDirectoryHandle(`bloques-${m.nombre}`, { create: true });
    const guardados = new Set();
    for await (const nombre of carpeta.keys()) guardados.add(Number(nombre));
    const total = Math.ceil(m.size / BLOQUE);
    const largo = (n) => Math.min(BLOQUE, m.size - n * BLOQUE);
    const memoria = new Map();  // el orden de inserción hace de LRU
    const enCamino = new Map();
    let ultimaFria = Date.now();  // última vez que el juego esperó un bloque fuera de la RAM

    // Cabeceras locales completas (30 bytes, nombre y extra), en el orden de m.posiciones
    const cabeceras = Uint8Array.from(atob(m.cabeceras), (c) => c.charCodeAt(0));
    const inicioCabecera = new Uint32Array(m.posiciones.length + 1);
    for (let k = 0, o = 0; k < m.posiciones.length; k++) {
      inicioCabecera[k] = o;
      o += 30 + (cabeceras[o + 26] | cabeceras[o + 27] << 8) + (cabeceras[o + 28] | cabeceras[o + 29] << 8);
      inicioCabecera[k + 1] = o;
    }

    // Solo con --diagnostico: qué partes de 64 KiB lee el juego (arranque.py arma la lista con
    // esto), cuánto espera y qué bloques bajó de la red
    const medida = { lecturas: 0, esperaMs: 0, opfs: 0, red: 0 };
    const tocados = new Set();
    let porRegistrar = [];
    const informar = (texto) => fetch(new URL('/log', m.url), { method: 'POST', body: texto }).catch(() => {});
    const registrar = (pos, len) => {
      for (let g = Math.floor(pos / 65536); g <= Math.floor((pos + len - 1) / 65536); g++) {
        if (tocados.has(g)) continue;
        tocados.add(g);
        if (porRegistrar.push(g) === 1) setTimeout(() => {
          const resumen = Object.entries(medida).map(([k, v]) => `${k}=${Math.round(v)}`).join(' ');
          informar(`[granos] ${porRegistrar.join(' ')} [medida] ${resumen}`);
          porRegistrar = [];
        }, 2000);
      }
    };

    const cargar = async (n) => {
      // Siempre se mira el disco: el core y la página llenan la misma carpeta, y `guardados`
      // del core se arma antes de que termine la precarga
      try {
        const archivo = await (await carpeta.getFileHandle(String(n))).getFile();
        if (archivo.size === largo(n)) {
          guardados.add(n);
          medida.opfs++;
          return new Uint8Array(await archivo.arrayBuffer());
        }
      } catch {}
      const inicio = performance.now();
      const datos = await pedir(m.url, n * BLOQUE, n * BLOQUE + largo(n));
      medida.red++;
      if (m.diag) informar(`[falta] bloque ${n} en ${Math.round(performance.now() - inicio)} ms`);
      try {
        const w = await (await carpeta.getFileHandle(String(n), { create: true })).createWritable();
        await w.write(datos);
        await w.close();
        guardados.add(n);
      } catch (e) {
        console.error(`[bloques] no se guardó el bloque ${n}`, e);  // sin disco igual se juega
      }
      return datos;
    };

    // enMemoria=false para lo que no se va a leer ahora: no saca del LRU lo que el juego usa
    const traer = async (n, enMemoria = true) => {
      if (memoria.has(n)) {
        const datos = memoria.get(n);
        memoria.delete(n);
        memoria.set(n, datos);
        return datos;
      }
      if (enMemoria) ultimaFria = Date.now();
      if (!enCamino.has(n)) enCamino.set(n, cargar(n).finally(() => enCamino.delete(n)));
      const datos = await enCamino.get(n);
      if (enMemoria) {
        memoria.set(n, datos);
        if (memoria.size > EN_MEMORIA) memoria.delete(memoria.keys().next().value);
      }
      return datos;
    };

    // Índice de la última cabecera que empieza en pos o antes
    const buscar = (pos) => {
      let a = 0, b = m.posiciones.length - 1;
      while (a < b) {
        const c = (a + b + 1) >> 1;
        if (m.posiciones[c] <= pos) a = c; else b = c - 1;
      }
      return m.posiciones[a] <= pos ? a : -1;
    };

    const leer = async (pos, len) => {
      len = Math.max(0, Math.min(len, m.size - pos));
      // Al abrir un archivo, el core lee la cabecera de todos los de su carpeta: 3 bytes y luego
      // 1024. Se responde desde el marcador hasta el fin de la cabecera, aunque pida más: una
      // lectura corta es válida y evita bajar un bloque por cada vecino.
      const i = buscar(pos);
      if (i >= 0 && pos < m.posiciones[i] + inicioCabecera[i + 1] - inicioCabecera[i]) {
        const ini = inicioCabecera[i] + pos - m.posiciones[i];
        return cabeceras.slice(ini, Math.min(ini + len, inicioCabecera[i + 1]));
      }
      const salida = new Uint8Array(len);
      const inicio = performance.now();
      medida.lecturas++;
      for (let hecho = 0; hecho < len;) {
        const p = pos + hecho, n = Math.floor(p / BLOQUE);
        const datos = await traer(n);
        const parte = datos.subarray(p - n * BLOQUE, p - n * BLOQUE + len - hecho);
        if (m.diag) registrar(p, parte.length);
        salida.set(parte, hecho);
        hecho += parte.length;
      }
      medida.esperaMs += performance.now() - inicio;
      return salida;
    };

    const enParalelo = async (bloques, hilos, avance, cederAlJuego = false) => {
      let siguiente = 0;
      const hilo = async () => {
        while (siguiente < bloques.length) {
          // No competir con el juego mientras carga un mapa o un combate
          while (cederAlJuego && Date.now() - ultimaFria < 3000) {
            await new Promise((listo) => setTimeout(listo, 500));
          }
          const n = bloques[siguiente++];
          if (!guardados.has(n)) await traer(n, false);
          avance?.(largo(n));
        }
      };
      await Promise.all(Array.from({ length: hilos }, hilo));
    };

    // Arranque: los bloques de los archivos que el juego lee al iniciar, y el directorio central
    const deArranque = [...m.arranque];
    for (let n = Math.floor(m.central / BLOQUE); n < total; n++) {
      if (!deArranque.includes(n)) deArranque.push(n);
    }

    let rellenando = false;
    return {
      size: m.size,
      leer,
      bytesArranque: deArranque.reduce((s, n) => s + largo(n), 0),
      precargar: (avance) => enParalelo(deArranque, 6, avance),
      // Baja el resto mientras se juega: la siguiente visita no espera la red
      rellenar: () => {
        if (rellenando) return;
        rellenando = true;
        enParalelo(Array.from({ length: total }, (_, n) => n), 2, null, true)
          .catch((e) => console.error('[bloques] relleno detenido', e));
      },
    };
  };

  return {
    abrir: (m) => {
      if (!abiertos.has(m.url)) abiertos.set(m.url, crear(m));
      return abiertos.get(m.url);
    },
    // El launcher nombra el archivo con la URL en base64url: el marcador no la repite
    urlDe: (nombre) => atob(nombre.replace(/\.mkxpz$/, '').replace(/-/g, '+').replace(/_/g, '/')),
  };
})();
