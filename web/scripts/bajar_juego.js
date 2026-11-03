// Baja el juego por trozos con Range: si se corta la conexión, al volver sigue donde iba.
// empaquetar.py lo antepone al launcher; el servidor debe aceptar Range.
window.__bajarJuego = async (url, avance) => {
  const TROZO = 64 * 1024 * 1024;
  const REINTENTOS = 8;
  const pedir = async (ini, fin) => {
    for (let intento = 1; ; intento++) {
      try {
        const r = await fetch(url, { headers: { Range: `bytes=${ini}-${fin}` } });
        if (r.status === 206) return r;
        throw new Error(`HTTP ${r.status}`);
      } catch (e) {
        if (intento === REINTENTOS) throw e;
        await new Promise((listo) => setTimeout(listo, 2 ** intento * 500));
      }
    }
  };

  const raiz = await navigator.storage.getDirectory();
  const carpeta = await raiz.getDirectoryHandle(`trozos-${url.split('/').pop()}`, { create: true });
  const prueba = await pedir(0, 0);
  const total = Number(prueba.headers.get('Content-Range').split('/')[1]);
  await prueba.arrayBuffer();

  const partes = [];
  for (let i = 0; i * TROZO < total; i++) {
    const largo = Math.min(TROZO, total - i * TROZO);
    const asa = await carpeta.getFileHandle(String(i), { create: true });
    let parte = await asa.getFile();
    if (parte.size !== largo) {
      const datos = await (await pedir(i * TROZO, i * TROZO + largo - 1)).blob();
      if (datos.size !== largo) throw new Error(`trozo ${i} incompleto`);
      const w = await asa.createWritable();
      await w.write(datos);
      await w.close();
      parte = await asa.getFile();
    }
    partes.push(parte);
    avance(largo);
  }
  // El launcher copia el Blob a su propio archivo, nombrado con la URL en base64url, y
  // recién entonces libera el disco: los trozos y el paquete de la versión anterior.
  const actual = `${btoa(url).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')}.mkxpz`;
  window.__borrarTrozos = async () => {
    const nombres = [];  // borrar mientras se recorre corta el recorrido
    for await (const nombre of raiz.keys()) nombres.push(nombre);
    for (const nombre of nombres) {
      if (nombre.startsWith('trozos-') || (nombre.endsWith('.mkxpz') && nombre !== actual)) {
        await raiz.removeEntry(nombre, { recursive: true });
      }
    }
  };
  return new Blob(partes);
};
