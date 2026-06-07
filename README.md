# Pokémon Infinite Fusion - Archipelago Multiworld Integration

¡Conecta Pokémon Infinite Fusion con Archipelago Multiworld! Juega de forma cooperativa con tus amigos mientras los objetos del suelo, de los NPCs y eventos están esparcidos por otros juegos.

## Estado del Proyecto
🚀 **Fase 2 Completada:** Soporte Multiworld bidireccional estable.
- **864 Ubicaciones** mapeadas.
- Sincronización en tiempo real vía WebSockets.
- Soporte nativo y no-bloqueante dentro de Ruby/RPG Maker XP.

---

## 🛠️ Requisitos
1. **Python 3.8+** instalado en tu PC.
2. El juego **Pokémon Infinite Fusion** (versión compatible probada: 5.3.x / E18).
3. Una instalación de [Archipelago](https://archipelago.gg/).

---

## ⚙️ Instalación y Configuración

### 1. Instalar el `.apworld`
1. Descarga el archivo `pokemon_infinite_fusion.apworld` de este repositorio.
2. Ve a la carpeta donde tienes instalado Archipelago.
3. Copia el archivo `.apworld` dentro de la ruta: `Archipelago/lib/custom_worlds/` (si no existe, créala).

### 2. Modificar el Juego (Infinite Fusion)
1. Copia el script `ArchipelagoNetwork.rb` dentro de la carpeta `Data/Scripts/052_AddOns/` de tu juego.
2. La próxima vez que abras el juego, el script inyectará automáticamente un Círculo Verde en la esquina superior derecha indicando el estado de conexión.

### 3. Ejecutar el Cliente Multiworld
El cliente es el intermediario entre tu juego local y el servidor de Archipelago.
1. Abre una terminal y navega hasta donde guardaste el proyecto.
2. Instala la dependencia necesaria ejecutando: `pip install websockets`.
3. Asegúrate de que los archivos `ap_local_client.py` y `client_mapping.json` estén en la misma carpeta.

---

## 🎮 ¿Cómo Jugar? (Pruebas)

1. **Generar el Mundo**:
   - Copia el archivo de ejemplo `pokemon_infinite_fusion.yaml` en la carpeta `Players` de Archipelago.
   - Ejecuta `ArchipelagoGenerate.exe` para crear tu semilla (*seed*).
   
2. **Iniciar el Servidor AP**:
   - En Archipelago, abre el archivo `.zip` generado (la *seed*) ejecutando `ArchipelagoServer.exe`.
   - Copia el puerto que te asigne el servidor (por defecto `38281`).

3. **Conectar el Cliente**:
   - Ejecuta el cliente de Python:
     ```bash
     python ap_local_client.py
     ```
   - (Asegúrate de editar `ap_local_client.py` en la línea 33 si tu servidor tiene contraseña o usa un puerto diferente. Por defecto es `ws://localhost:38281` y slot `Player1`).

4. **Jugar**:
   - Abre *Pokémon Infinite Fusion*. 
   - El círculo en la esquina pasará de Rojo a **Verde**.
   - ¡Ve a recoger una Poción en la Ruta 1! El cliente Python reportará la ubicación automáticamente al servidor de Archipelago.

---

## 🏗️ Arquitectura Técnica

- **`AP_Extractor.rb`**: (Herramienta de desarrollo) Escaneó en tiempo real los mapas del juego para extraer los metadatos y compilar el JSON original.
- **`apworld_generator.py`**: Compila el JSON extraído, elimina duplicados y genera los archivos nativos de Archipelago (`locations.py`, `items.py`, `options.py`).
- **Ruby Network Hooks**: Modificación de `pbItemBall` y `pbReceiveItem` preservando los métodos originales.
- **Async Python Client**: Puente con dos hilos, `http.server` síncrono para el juego y `asyncio + websockets` asíncrono para el AP Server.
