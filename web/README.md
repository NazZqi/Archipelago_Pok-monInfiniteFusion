# Pokémon Infinite Fusion en el navegador

Corre el juego real con el core web de mkxp-z (WebAssembly). Solo para escritorio: cada jugador necesita unos 1,5 GB de memoria.

**Este directorio no contiene archivos del juego ni el paquete generado**, y el paquete no debe entrar al repo. Se sirve solo con sesión iniciada.

## Requisitos

- Una instalación de PIF (probado con 6.8.3).
- Python 3 con `pillow` y `pyoxipng`, y `ffmpeg` en el `PATH`.
- El launcher y el core publicados por [mkxp-z-libretro-emscripten](https://github.com/white-axe/mkxp-z-libretro-emscripten) ([PR 255](https://github.com/mkxp-z/mkxp-z/pull/255), commit `5cd3203`) en una carpeta `sitio/`. El core es GPL-2.0: conserva el enlace a su código fuente en la página.

## Generar el paquete

```bat
python web\tools\parchear_core.py core sitio
python web\tools\bajar_sprites.py sprites-base
python web\tools\empaquetar.py InfiniteFusion sitio --sprites sprites-base --cache reducidos --arranque web\arranque.txt
```

La primera vez tarda unos 40 minutos: `reducidos/` guarda el audio y los PNG procesados, y las siguientes los reutilizan. El resultado queda en `sitio/`: el paquete `pif-<hash>.mkxpz` y su marcador `pif-<hash>.json`. Con `--diagnostico` el paquete incluye `web_diag.rb` (medidor de FPS y un canal `eval`) y el launcher admite `#auto`: **nunca lo publiques así**.

### Descarga por partes

Como Last Havens, el juego no baja entero antes de arrancar:

1. El launcher guarda en OPFS el marcador en lugar del paquete. El marcador trae las cabeceras locales del zip: al abrir un archivo, el core lee la de cada vecino de su carpeta.
2. La página baja con `Range` los bloques de arranque, unos 76 MiB.
3. El core lee el resto del paquete por bloques de 256 KiB a medida que los necesita (`web/scripts/bloques.js`). Los guarda en OPFS.
4. Mientras se juega, el resto llega en segundo plano. La segunda visita no usa la red.

`web/arranque.txt` lista los archivos que el juego lee al iniciar; van primero en el paquete. Si cambia el juego, se vuelve a grabar:

1. Genera el paquete con `--diagnostico` y sin `--arranque`.
2. Abre el juego en un perfil limpio, hasta el título.
3. Corre `python web\tools\arranque.py sitio\pif-<hash>.mkxpz corridas.log > web\arranque.txt`.

Medido con 60 ms y 20 Mbps simulados por pedido:
- La primera visita llega al primer frame en unos 40 s (antes bajaba 1 GB).
- Un archivo que falta tarda unos 0,2 s.
- El resto queda completo en unos 5 minutos de juego.

## Servidor

`web/server.mjs` (Node 22, sin dependencias):
- Valida la cuenta con Nextcloud y entrega el juego solo con sesión.
- Guarda por cuenta las partidas y las teclas, con 10 versiones.
- Recibe los reportes de fallos y retransmite las posiciones de los jugadores visibles.

```bash
NEXTCLOUD_URL=https://nube.cinderlink.cl PIF_JUEGO=sitio PIF_DATOS=/mnt/datos/pif ORIGEN=https://juego.cinderlink.cl node web/server.mjs
```

`web/public/` es la página de entrada: login, botón Jugar, PWA y `offline.html`. El launcher queda en `/juego/`. `web/scripts/juego.js` se antepone al launcher y hace cuatro cosas:
- Antes de arrancar, baja los archivos del jugador. Si una partida local cambió sin subirse y el servidor también, guarda aparte la copia local.
- Sube lo que el juego guarda.
- Avisa los fallos.
- Hace de puente entre `/api/red` y `web_red.rb`.

Pruebas: `node --test web/test/`.

## Qué cambia respecto al juego nativo

| Pieza | Motivo |
|---|---|
| `parchear_core.py` | Reserva 1,125 GiB para el sandbox: con la original, `realloc` agota el heap de 2 GiB y el juego cae con `Sandbox trap`. Agrega un búfer de lectura: montar el paquete pasa de 70 a 2 s, y abrir una carpeta grande por primera vez, de 2 a 1 s. |
| `web_compat.rb` | Adapta Ruby 3.3, simula `HTTPLite` sin red, rearma la entrada de teclado, reemplaza `pathCache` con una tabla de rutas y lee `load_data` de una vez (51 a 5 s en las animaciones de combate). |
| `web_final.rb` | Desactiva las descargas, que dejan el sprite en `?` aunque la hoja esté en el paquete, y el descifrado de `.dat`. Lee las hojas autogeneradas por tiras. |
| `.dat` descifrados | PIF los descifra byte a byte en Ruby: 45 s solo con `messages.dat`. |
| `messages.dat` sin `""` | Sus 4 arrays de un millón de strings vacíos pasan a `nil`: de 31 a 7 MB, y de 8 a 1,5 s al cargarlo. |
| Hojas autogeneradas en tiras | Cada hoja de 960×5568 pasa a 12 tiras de 5 filas, en una carpeta por hoja. Decodificarla entera costaba 800 ms por sprite, y una sola carpeta con todas las tiras congelaba hasta 20 s. |
| PNG con oxipng | Sin pérdida: las hojas autogeneradas bajan 45%. |
| `Data/sprites/CUSTOM_SPRITES` y `Data/pokedex/dex.json` vacíos | Lista y entradas de sprites custom, que no están en el paquete. La intro usa fusiones autogeneradas (`web_final.rb`). |
| Sin `messages_fr.dat`, `attacksRS.dat` ni `Sprite Credits.csv` | Ningún script ni evento los lee. |
| `bajar_sprites.py` | El juego no trae los sprites base; los pide a infinitefusion.net al usarlos. |
| `bloques.js` y `bajar_juego.js` | El paquete se lee por bloques con `Range` y queda en OPFS: ver "Descarga por partes". |
| `web_red.rb` | Jugadores visibles. Dibuja con `ArchipelagoRemotePlayers.rb` del mod de Archipelago; `juego.js` lleva las posiciones por archivos. |
| Audio reducido | BGM y ME en MP3 a 96 kbps, y los WAV de BGM a Vorbis. Los sprites custom no se incluyen: las fusiones usan los autogenerados. |

## Fuera por ahora

Archipelago no funciona aquí: `client.py` necesita Python y el juego no tiene red. Tampoco hay Wonder Trade ni bases secretas.
