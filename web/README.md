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
python web\tools\empaquetar.py InfiniteFusion sitio --sprites sprites-base --cache reducidos
```

La primera vez tarda unos 40 minutos: `reducidos/` guarda el audio y los PNG procesados, y las siguientes los reutilizan. El resultado queda en `sitio/pif-<hash>.mkxpz`. El servidor debe enviar COOP/COEP y aceptar `Range`. Con `--diagnostico` el paquete incluye `web_diag.rb` (medidor de FPS y un canal `eval`) y el launcher admite `#auto`: **nunca lo publiques así**.

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
| `bajar_juego.js` | Baja por trozos de 64 MB con `Range`, y sigue donde iba si se corta. |
| Audio reducido | BGM y ME en MP3 a 96 kbps, y los WAV de BGM a Vorbis. Los sprites custom no se incluyen: las fusiones usan los autogenerados. |

## Fuera por ahora

Archipelago y los jugadores visibles no funcionan aquí: `client.py` necesita Python y el juego no tiene red. Tampoco hay Wonder Trade ni bases secretas.
