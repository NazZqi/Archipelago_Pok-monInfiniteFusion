// En vez del paquete entero, el launcher guarda en OPFS el marcador pif-<hash>.json, y el
// core lee el paquete por bloques (bloques.js). Aquí se baja solo el arranque, con avance.
// empaquetar.py lo antepone al launcher, después de bloques.js.
window.__bajarJuego = async (url, avance) => {
  const r = await fetch(url.replace(/\.mkxpz$/, '.json'));
  if (!r.ok) throw new Error(`marcador: HTTP ${r.status}`);
  const texto = await r.text();
  const marcador = JSON.parse(texto);
  const paquete = await __paqueteRemoto.abrir({ ...marcador, url });
  // El launcher mide el avance contra el tamaño del marcador, no del arranque
  const escala = texto.length / paquete.bytesArranque;
  await paquete.precargar((bytes) => avance(bytes * escala));

  const raiz = await navigator.storage.getDirectory();
  const actual = `${btoa(url).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')}.mkxpz`;
  const bloques = `bloques-${marcador.nombre}`;
  // El launcher llama esto tras copiar el marcador: libera lo de versiones anteriores
  window.__borrarViejos = async () => {
    const nombres = [];  // borrar mientras se recorre corta el recorrido
    for await (const nombre of raiz.keys()) nombres.push(nombre);
    for (const nombre of nombres) {
      // La carpeta de bloques también termina en .mkxpz: se mira antes que los paquetes
      const viejo = nombre.startsWith('bloques-') ? nombre !== bloques
        : nombre.startsWith('trozos-') || (nombre.endsWith('.mkxpz') && nombre !== actual);
      if (viejo) {
        await raiz.removeEntry(nombre, { recursive: true });
      }
    }
  };
  return new Blob([texto]);
};
