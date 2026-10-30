# Pokémon Infinite Fusion - Archipelago Multiworld Integration

![Archipelago](https://img.shields.io/badge/Archipelago-Multiworld-blue)
![Pokémon Infinite Fusion](https://img.shields.io/badge/Pok%C3%A9mon-Infinite%20Fusion-red)
![Status](https://img.shields.io/badge/Estado-Beta_Estable-brightgreen)

¡Conecta Pokémon Infinite Fusion con Archipelago Multiworld! Juega de forma cooperativa con tus amigos mientras los objetos del suelo, de los NPCs y eventos están esparcidos por otros juegos.

## Estado del Proyecto
🚀 **Integración Core Completada:** Soporte Multiworld bidireccional estable.
- Estructura `.apworld` nativa para Archipelago.
- **Generación automatizada de objetos y ubicaciones** mapeadas.
- Sincronización en tiempo real.
- Soporte nativo y no-bloqueante dentro de Ruby/RPG Maker XP.
- Soporte de cliente nativo integrado en el `.apworld`.

---

## 🛠️ Requisitos
1. **Python 3.8+** instalado en tu PC.
2. El juego **Pokémon Infinite Fusion** (versión compatible probada: 5.3.x / E18).
3. Una instalación de [Archipelago](https://archipelago.gg/).

---

## ⚙️ Instalación y Configuración

### 1. Preparar Archipelago (El Servidor/Generador)
1. Descarga el archivo `pokemon_infinite_fusion.apworld` desde la pestaña de Releases.
2. Copia este archivo en la carpeta `custom_worlds` de tu instalación de Archipelago (generalmente en `C:\ProgramData\Archipelago\custom_worlds` o `Archipelago/lib/custom_worlds/`). Si la carpeta no existe, créala.
3. Descarga la plantilla `Pokemon Infinite Fusion.yaml`, configúrala a tu gusto y ponla en la carpeta `Players` de tu Archipelago para generar la semilla (seed).

### 2. Instalar el Mod en el Juego (El Cliente)
Hemos creado un instalador automático para que conectar tu juego con Archipelago sea sumamente sencillo.
1. Descarga el archivo **`PokemonIF_AP_ClientMod.zip`** desde la pestaña de Releases.
2. Descomprime su contenido directamente en la carpeta raíz de tu juego Pokémon Infinite Fusion (la misma carpeta donde se encuentra el archivo `Game.exe`).
3. Haz doble clic en el archivo **`Instalar-Archipelago.bat`**. 
4. El script comprobará las carpetas y copiará automáticamente los archivos necesarios a `Data/Scripts/998_Experimental`.
5. ¡Listo! Al abrir el juego verás un indicador visual (Círculo Verde/Rojo) en la esquina superior derecha que indica el estado de conexión con el cliente de Archipelago.

---

## 🎮 ¿Cómo Jugar?

1. **Configurar la Semilla**:
   - Edita el archivo `Pokemon Infinite Fusion.yaml` para ajustar tus preferencias (las opciones principales ahora utilizan valores True/False).
   - ¡Prueba la nueva opción **`Randomize Everything`** si quieres el máximo nivel de caos!
   - Copia el archivo `.yaml` en la carpeta `Players` de Archipelago.

2. **Generar el Mundo**:
   - Ejecuta `ArchipelagoGenerate.exe` para crear tu semilla (*seed*).
   
3. **Iniciar el Servidor AP**:
   - En Archipelago, abre el archivo `.zip` generado (la *seed*) ejecutando `ArchipelagoServer.exe`.
   - Copia el puerto que te asigne el servidor (por defecto `38281`).

4. **Conectar el Cliente**:
   - Ejecuta el cliente nativo de Archipelago (usualmente desde el Launcher, abriendo el Pokemon Infinite Fusion Client) y conéctate al servidor. El cliente se encarga de crear el puente entre el servidor de AP y el juego abierto.

5. **Jugar**:
   - Abre *Pokémon Infinite Fusion*. 
   - El círculo en la esquina pasará de Rojo a **Verde** al conectar con el cliente puente.
   - ¡Explora y juega! Ahora los eventos importantes, el `Pokedex`, y la victoria (al ganar el evento `Defeat Champion`) están completamente integrados y sincronizados con Archipelago.

---

## 🏗️ Arquitectura Técnica

- **Estructura APWorld**: Contiene la lógica de regiones (`regions.py`), reglas lógicas (`rules.py`), ubicaciones (`locations.py`), objetos (`items.py`) y el mapeo de IDs (`map_ids.py`).
- **`apworld_generator.py`**: Utilidad para compilar los JSON extraídos del juego base y generar el código nativo para el apworld.
- **Cliente Nativo (`client.py`)**: Totalmente integrado en el `.apworld`, estableciendo el puente (http local / websockets) hacia el servidor de AP.
- **Ruby Network Hooks**: Modificación de eventos base de in-game (obtención de objetos, combate, etc.) para comunicarse sin bloquear el hilo de ejecución de RPG Maker XP.

---

## 👩‍💻 Desarrollo

El repositorio **no incluye el juego**. Para desarrollar, copia tu instalación de Pokémon Infinite Fusion en la carpeta `pokemon/` de la raíz del repo (está en `.gitignore`).

- `releases/998_Experimental/` es la fuente de los scripts Ruby. Para probarlos en el juego:
  `xcopy /E /I /Y releases\998_Experimental pokemon\Data\Scripts\998_Experimental`
- `archipelago/apworld_generator.py` regenera `items.py` y `client_items.json` desde `pokemon/ap_items_dump.json` (exportado por `ExportAPItems.rb`).
- `archipelago/generate_locations_py.py` regenera `locations.py` y `client_mapping.json` desde `pokemon/Data/ap_locations_classified.json` (exportado por `ExportAPLocations.rb`).
- `archipelago/fix_maps.py` reasigna mapas a regiones en `map_ids.py` usando `archipelago/map_dump.json`.
- `archipelago/build_apworld.py` empaqueta `releases/pokemon_infinite_fusion.apworld`.

¡Diviértete fusionando y colaborando en Archipelago!
