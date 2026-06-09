# Pokémon Infinite Fusion - Archipelago Multiworld Integration

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

### 1. Instalar el `.apworld`
Puedes compilar el archivo `.apworld` usando el script incluido o descargar la versión ya empaquetada.
1. Ejecuta `python build_apworld.py` para generar e instalar automáticamente el `pokemon_infinite_fusion.apworld` en la carpeta `custom_worlds` de tu Archipelago local.
2. O bien, descarga el archivo precompilado y cópialo manualmente en `Archipelago/lib/custom_worlds/` (si no existe, créala).

### 2. Modificar el Juego (Infinite Fusion)
1. Copia el script de red correspondiente dentro de la carpeta `Data/Scripts/052_AddOns/` de tu juego (las instrucciones detalladas para el parche de Ruby se proporcionan en la release).
2. La próxima vez que abras el juego, el script inyectará automáticamente un indicador visual (Círculo Verde/Rojo) en la esquina superior derecha indicando el estado de conexión local.

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

¡Diviértete fusionando y colaborando en Archipelago!
