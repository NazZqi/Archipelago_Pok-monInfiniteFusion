#=============================================================================
# ** Módulo ArchipelagoNetwork
#-----------------------------------------------------------------------------
# Módulo de comunicación HTTP para la integración de Archipelago con
# Pokémon Infinite Fusion. Se conecta a un servidor local en 127.0.0.1:5050
# y envía notificaciones de eventos del juego vía HTTPLite.
#
# Protocolo: HTTP + JSON
#   POST /event  — Enviar eventos al servidor
#   GET  /poll   — Recibir ítems/comandos del servidor
#
# IMPORTANTE: Toda operación de red está envuelta en begin/rescue para
# garantizar que el juego NUNCA crashee por problemas de conexión.
#=============================================================================

#=============================================================================
# Parche de compatibilidad para AnimatedBitmap (Evitar crasheos con ítems sin ícono)
#=============================================================================
class AnimatedBitmap
  alias _ap_initialize_old initialize unless method_defined?(:_ap_initialize_old)
  def initialize(file, hue = 0)
    if file == ""
      @filename = ""
      @path = ""
      @bitmap = GifBitmap.new("", "", hue)
      return
    end
    _ap_initialize_old(file, hue)
  end
end

module ArchipelagoNetwork
  #---------------------------------------------------------------------------
  # Configuración
  #---------------------------------------------------------------------------
  BASE_URL = "http://127.0.0.1:5050"
  LOG_FILE = "Data/archipelago.log"

  # Intervalo mínimo entre intentos de reconexión (en segundos)
  RECONEXION_COOLDOWN = 10

  # Intervalo mínimo entre polls al servidor (en frames, ~40fps)
  POLL_INTERVAL_FRAMES = 120  # cada ~3 segundos

  # Máximo de errores consecutivos antes de desactivar temporalmente
  MAX_ERRORES_CONSECUTIVOS = 5

  #---------------------------------------------------------------------------
  # Estado interno (variables de módulo)
  #---------------------------------------------------------------------------
  @conectado = false
  @ultimo_error = nil
  @ultimo_intento_conexion = 0
  @errores_consecutivos = 0
  @deshabilitado = false
  @mensajes_enviados = 0
  @frames_desde_ultimo_poll = 0
  @recibiendo_de_servidor = false
  @medallas_conocidas = []
  @latencia = 0
  @mensajes_pendientes = []
  @items_pendientes = []

  #---------------------------------------------------------------------------
  # Métodos de clase
  #---------------------------------------------------------------------------
  class << self
    attr_accessor :recibiendo_de_servidor
    attr_accessor :latencia
    attr_accessor :mensajes_pendientes
    attr_accessor :items_pendientes
    #=========================================================================
    # log_archivo
    #-------------------------------------------------------------------------
    # Escribe un mensaje al archivo de log (funciona SIN $DEBUG).
    #=========================================================================
    def log_archivo(msg)
      begin
        File.open(LOG_FILE, "a") do |f|
          f.puts "[#{Time.now.strftime('%H:%M:%S')}] #{msg}"
        end
      rescue Exception => e
        # Si ni siquiera podemos escribir el log, no hacer nada
      end
    end

    #=========================================================================
    # conectar
    #-------------------------------------------------------------------------
    # Intenta verificar la conexión con el servidor AP local via HTTP.
    # Retorna: true si el servidor responde, false si no.
    #=========================================================================
    def conectar
      return false if @deshabilitado
      return true if @conectado

      # Cooldown entre intentos de reconexión
      ahora = Time.now.to_i
      if (ahora - @ultimo_intento_conexion) < RECONEXION_COOLDOWN
        return false
      end
      @ultimo_intento_conexion = ahora

      begin
        log_archivo "Intentando conectar a #{BASE_URL}..."
        echoln "[Archipelago] Intentando conectar a #{BASE_URL}..."

        # Enviar mensaje de conexión inicial via POST
        body = hash_to_json({"type" => "connected", "game" => "Pokemon Infinite Fusion"})
        response = HTTPLite.post_body(
          BASE_URL + "/event",
          body,
          "application/json"
        )

        if response.is_a?(Hash) && response[:status] == 200
          @conectado = true
          @errores_consecutivos = 0
          @ultimo_error = nil

          log_archivo "¡Conectado exitosamente al servidor AP!"
          echoln "[Archipelago] ¡Conectado exitosamente!"
          return true
        else
          status = response.is_a?(Hash) ? response[:status] : "???"
          @ultimo_error = "Servidor respondió con status: #{status}"
          log_archivo @ultimo_error
          echoln "[Archipelago] #{@ultimo_error}"
          registrar_error
          return false
        end

      rescue Exception => e
        @ultimo_error = "Error de conexión: #{e.class} - #{e.message}"
        log_archivo @ultimo_error
        echoln "[Archipelago] #{@ultimo_error}"
        registrar_error
        return false
      end
    end

    #=========================================================================
    # desconectar
    #-------------------------------------------------------------------------
    # Marca la conexión como cerrada.
    #=========================================================================
    def desconectar
      @conectado = false
      log_archivo "Desconectado."
      echoln "[Archipelago] Desconectado."
    end

    #=========================================================================
    # conectado?
    #-------------------------------------------------------------------------
    # Retorna true si hay una conexión activa.
    #=========================================================================
    def conectado?
      return @conectado
    end

    #=========================================================================
    # enviar_ubicacion (método principal para hooks)
    #-------------------------------------------------------------------------
    # Envía un evento de "ítem encontrado" al servidor AP.
    #   item_name : String — nombre interno del ítem (ej: "POTION")
    #   cantidad  : Integer — cantidad obtenida
    #   map_id    : Integer — ID del mapa actual
    #=========================================================================
    def enviar_ubicacion(item_name, cantidad = 1, map_id = 0, event_id = 0)
      return if @deshabilitado

      mensaje = {
        "type"     => "item_found",
        "item"     => item_name.to_s,
        "quantity" => cantidad,
        "map_id"   => map_id,
        "event_id" => event_id
      }

      return enviar_mensaje(mensaje)
    end

    #=========================================================================
    # enviar_evento_recibido
    #-------------------------------------------------------------------------
    # Envía notificación de que el jugador recibió un ítem (ej: via NPC).
    #=========================================================================
    def enviar_evento_recibido(item_name, cantidad = 1, map_id = 0, event_id = 0)
      return if @deshabilitado

      mensaje = {
        "type"     => "item_received",
        "item"     => item_name.to_s,
        "quantity" => cantidad,
        "map_id"   => map_id,
        "event_id" => event_id
      }

      return enviar_mensaje(mensaje)
    end

    #=========================================================================
    # enviar_meta
    #-------------------------------------------------------------------------
    # Avisa al cliente de Archipelago que el juego ha sido completado.
    # Llama a este método en el evento de la Liga Pokémon o al final del juego.
    # Uso en evento RPG Maker: ArchipelagoNetwork.enviar_meta
    #=========================================================================
    def enviar_meta
      return if @deshabilitado || !conectado?

      begin
        log_archivo "Enviando evento de Meta (Victoria) a Archipelago..."
        echoln "[Archipelago] ¡Meta completada enviada al servidor!"

        # El cliente Python escucha en /goal
        response = HTTPLite.post_body(
          BASE_URL + "/goal",
          "{}",
          "application/json"
        )

        if response.is_a?(Hash) && response[:status] == 200
          log_archivo "Meta registrada con éxito en el cliente."
          return true
        else
          log_archivo "Error al enviar meta, status: #{response[:status]}"
          return false
        end
      rescue Exception => e
        log_archivo "Excepción al enviar meta: #{e.message}"
        return false
      end
    end

    #=========================================================================
    # poll_servidor
    #-------------------------------------------------------------------------
    # Lee datos del servidor via HTTP GET (no-bloqueante, con rate limiting).
    # Retorna: Hash con datos recibidos, o nil si no hay nada.
    #=========================================================================
    def poll_servidor
      # Intentar reconectar automáticamente si no está conectado
      conectar unless conectado?
      return nil unless conectado?

      # Rate limiting por frames
      @frames_desde_ultimo_poll += 1
      return nil if @frames_desde_ultimo_poll < POLL_INTERVAL_FRAMES
      @frames_desde_ultimo_poll = 0

      begin
        start_time = Time.now
        response = HTTPLite.get(BASE_URL + "/poll")
        @latencia = ((Time.now - start_time) * 1000).to_i

        if response.is_a?(Hash) && response[:status] == 200
          data = HTTPLite::JSON.parse(response[:body])
          events = data["events"]
          if events && events.is_a?(Array) && events.size > 0
            log_archivo "Recibidos #{events.size} eventos del servidor"
            echoln "[Archipelago] Recibidos #{events.size} eventos del servidor"
            return data
          end
          return nil
        else
          # Servidor no disponible, marcar desconectado
          desconectar
          return nil
        end

      rescue Exception => e
        log_archivo "Error al hacer poll: #{e.class} - #{e.message}"
        echoln "[Archipelago] Error al leer: #{e.class} - #{e.message}"
        desconectar
        return nil
      end
    end

    #=========================================================================
    # procesar_eventos_servidor
    #-------------------------------------------------------------------------
    # Llama a poll_servidor y procesa los comandos inyectados por la red.
    #=========================================================================
    def procesar_eventos_servidor
      datos = poll_servidor
      return unless datos && datos["events"]

      @recibiendo_de_servidor = true
      
      datos["events"].each do |evento|
        action = evento["action"]
        
        if action == "set_options"
          $ArchipelagoOptions = evento["options"]
          ArchipelagoNetwork.log_archivo "Opciones recibidas desde Archipelago: #{$ArchipelagoOptions.inspect}"
          
          # Map options to Pokémon Infinite Fusion internal switches
          opts = $ArchipelagoOptions
          if $game_switches
            $game_switches[778]  = true if opts["wild_pokemon"] && opts["wild_pokemon"] > 0
            $game_switches[987]  = true if opts["trainer_parties"] && opts["trainer_parties"] > 0
            $game_switches[954]  = true if opts["starters"] && opts["starters"] > 0
            $game_switches[1031] = true if opts["legendary_encounters"] && opts["legendary_encounters"] > 0
            $game_switches[780]  = true if opts["npc_gifts"] && opts["npc_gifts"] > 0
            $game_switches[751]  = true if opts["overworld_items"] && opts["overworld_items"] > 0
            $game_switches[755]  = true if opts["overworld_items"] && opts["overworld_items"] > 0
            $game_switches[921]  = true if opts["types"] && opts["types"] > 0
            $game_switches[855]  = true # SWITCH_RANDOMIZED_AT_LEAST_ONCE
            
            $game_map.need_refresh = true if $game_map
          end
          
          next
        end

        # Retrocompatibilidad o ítems
        if action == "give_item" || evento["item"]
          item_id = evento["item"]
          cantidad = (evento["quantity"] || 1).to_i
          display_name = evento["name"] || item_id
          
          item_obj = GameData::Item.try_get(item_id)
          if item_obj
            log_archivo "Encolando ítem de AP para el jugador: #{item_obj.id} x#{cantidad}"
            @items_pendientes ||= []
            @items_pendientes.push({item: item_obj.id, quantity: cantidad, name: display_name})
          else
            log_archivo "Ítem desconocido del servidor: #{item_id}"
            @mensajes_pendientes.push("¡Recibiste un objeto misterioso de AP! (#{item_id})")
          end
          
        elsif action == "give_badge"
          badge_id = (evento["badge_id"] || 0).to_i
          display_name = evento["name"] || "Medalla #{badge_id}"
          if $Trainer && $Trainer.badges
            $Trainer.badges[badge_id] = true
            @medallas_conocidas[badge_id] = true
            @mensajes_pendientes.push("¡Has recibido #{display_name} de Archipelago!")
          end
          
        elsif action == "give_pokemon"
          species = evento["species"]
          if species
            species = species.to_sym if species.is_a?(String)
            pbAddPokemonSilent(species, 5) 
            @mensajes_pendientes.push("¡Un Pokémon materializado por Archipelago se ha unido a tu equipo!")
          end
          
        elsif action == "chat_message"
          msg = evento["text"] || ""
          @mensajes_pendientes.push(msg) if msg.length > 0
        end
      end
      
      @recibiendo_de_servidor = false
    rescue Exception => e
      @recibiendo_de_servidor = false
      log_archivo "Error procesando eventos: #{e.message}"
    end

    #=========================================================================
    # revisar_medallas
    #-------------------------------------------------------------------------
    # Monitorea $Trainer.badges para enviar un evento si hay una nueva medalla.
    #=========================================================================
    def revisar_medallas
      return if $Trainer.nil? || $Trainer.badges.nil?
      
      # Inicializar el arreglo la primera vez
      if @medallas_conocidas.empty?
        @medallas_conocidas = $Trainer.badges.clone
        return
      end

      # Comparar el estado actual con el conocido
      $Trainer.badges.each_with_index do |tiene_medalla, index|
        if tiene_medalla && !@medallas_conocidas[index]
          # ¡Detectamos una medalla nueva!
          enviar_mensaje({
            "type" => "badge_obtained",
            "badge_id" => index
          })
          @medallas_conocidas[index] = true
        end
      end
    end

    #=========================================================================
    # estado
    #-------------------------------------------------------------------------
    # Retorna un hash con el estado actual de la conexión (para debug).
    #=========================================================================
    def estado
      {
        conectado: conectado?,
        deshabilitado: @deshabilitado,
        errores_consecutivos: @errores_consecutivos,
        ultimo_error: @ultimo_error,
        mensajes_enviados: @mensajes_enviados
      }
    end

    #=========================================================================
    # reactivar
    #-------------------------------------------------------------------------
    # Reactiva el módulo después de haber sido deshabilitado por errores.
    #=========================================================================
    def reactivar
      @deshabilitado = false
      @errores_consecutivos = 0
      @ultimo_intento_conexion = 0
      log_archivo "Módulo reactivado. Se intentará reconectar."
      echoln "[Archipelago] Módulo reactivado. Se intentará reconectar."
    end

    private

    #=========================================================================
    # enviar_mensaje (interno)
    #-------------------------------------------------------------------------
    # Envía un hash como JSON via HTTP POST al servidor.
    # Intenta reconectar si es necesario.
    #=========================================================================
    def enviar_mensaje(mensaje_hash)
      # Intentar reconectar si no estamos conectados
      if !conectado?
        return false unless conectar
      end

      return enviar_raw(mensaje_hash)
    end

    #=========================================================================
    # enviar_raw (interno)
    #-------------------------------------------------------------------------
    # Envía datos al servidor via HTTP POST.
    #=========================================================================
    def enviar_raw(mensaje_hash)
      begin
        body = hash_to_json(mensaje_hash)

        response = HTTPLite.post_body(
          BASE_URL + "/event",
          body,
          "application/json"
        )

        if response.is_a?(Hash) && response[:status] == 200
          @mensajes_enviados += 1
          @errores_consecutivos = 0

          tipo = mensaje_hash["type"] || "???"
          if tipo != "heartbeat"
            log_archivo "Enviado: #{tipo} — #{body}"
            echoln "[Archipelago] Enviado: #{tipo}"
          end
          
          parsed = HTTPLite::JSON.parse(response[:body]) rescue {}
          return parsed
        else
          status = response.is_a?(Hash) ? response[:status] : "???"
          log_archivo "Error del servidor al enviar (status #{status})"
          echoln "[Archipelago] Error del servidor: status #{status}"
          desconectar
          registrar_error
          return false
        end

      rescue Exception => e
        log_archivo "Error al enviar: #{e.class} - #{e.message}"
        echoln "[Archipelago] Error al enviar: #{e.class} - #{e.message}"
        desconectar
        registrar_error
        return false
      end
    end

    #=========================================================================
    # registrar_error (interno)
    #-------------------------------------------------------------------------
    # Incrementa el contador de errores y desactiva si excede el máximo.
    #=========================================================================
    def registrar_error
      @errores_consecutivos += 1
      if @errores_consecutivos >= MAX_ERRORES_CONSECUTIVOS
        @deshabilitado = true
        log_archivo "Demasiados errores consecutivos (#{MAX_ERRORES_CONSECUTIVOS}). Módulo DESHABILITADO."
        echoln "[Archipelago] Demasiados errores consecutivos (#{MAX_ERRORES_CONSECUTIVOS})."
        echoln "[Archipelago] Módulo DESHABILITADO. Usa ArchipelagoNetwork.reactivar para reintentar."
      end
    end

    #=========================================================================
    # hash_to_json (interno)
    #-------------------------------------------------------------------------
    # Convierte un Hash a JSON string manualmente.
    # MKXP-z puede no tener 'json' como gem, así que lo hacemos a mano.
    #=========================================================================
    def hash_to_json(hash)
      pairs = hash.map do |key, value|
        k = "\"#{escape_json_string(key.to_s)}\""
        v = case value
            when String
              "\"#{escape_json_string(value)}\""
            when Integer, Float
              value.to_s
            when TrueClass
              "true"
            when FalseClass
              "false"
            when NilClass
              "null"
            else
              "\"#{escape_json_string(value.to_s)}\""
            end
        "#{k}:#{v}"
      end
      "{#{pairs.join(",")}}"
    end

    #=========================================================================
    # escape_json_string (interno)
    #-------------------------------------------------------------------------
    # Escapa caracteres especiales para JSON.
    #=========================================================================
    def escape_json_string(str)
      str.gsub("\\", "\\\\")
         .gsub("\"", "\\\"")
         .gsub("\n", "\\n")
         .gsub("\r", "\\r")
         .gsub("\t", "\\t")
    end
  end
end

#=============================================================================
# ** Hook de pbItemBall — Intercepta la obtención de ítems del suelo
#=============================================================================
# Usamos alias para envolver la función original sin modificar el archivo
# base de Overworld. La función original se preserva completamente.
#=============================================================================

# Guardar referencia a la función original
alias pbItemBall_sin_archipelago pbItemBall unless defined?(pbItemBall_sin_archipelago)

def pbItemBall(item, quantity = 1, item_name = "", canRandom = true)
  # Si Archipelago indica no randomizar ítems del suelo, pasamos al nativo
  if $ArchipelagoOptions && $ArchipelagoOptions["randomize_item_balls"] == 0
    return pbItemBall_sin_archipelago(item, quantity, item_name, canRandom)
  end

  # Si Archipelago está conectado, bloqueamos el ítem original
  if ArchipelagoNetwork.conectado?
    begin
      current_map = $game_map ? $game_map.map_id : 0
      event_id = 0
      if $game_system && $game_system.map_interpreter
        event_id = $game_system.map_interpreter.instance_variable_get(:@event_id) || 0
      end

      # Resolver el nombre real del ítem para el log
      item_data = GameData::Item.try_get(item)
      item_id = item_data ? item_data.id.to_s : item.to_s

      # Notificar a AP sobre esta ubicación
      resp = ArchipelagoNetwork.enviar_ubicacion(item_id, quantity, current_map, event_id)

      if resp && resp["tracked"] == true
        # Reproducir sonido de obtención y desaparecer la Pokéball
        pbSEPlay("Pokemon get")
        Kernel.pbMessage(_INTL("\\se[Pokemon get]¡Encontraste un objeto para Archipelago!"))

        # Desaparecer el evento del mapa (la Pokéball visual)
        if $game_system && $game_system.map_interpreter
          evid = $game_system.map_interpreter.instance_variable_get(:@event_id)
          if evid && evid > 0
            $game_self_switches[[$game_map.map_id, evid, "A"]] = true
            $game_map.need_refresh = true
          end
        end
        return true
      else
        return pbItemBall_sin_archipelago(item, quantity, item_name, canRandom)
      end
    rescue Exception => e
      ArchipelagoNetwork.log_archivo "Error en hook pbItemBall AP: #{e.message}"
      # Fallback: dar el ítem normal si algo falla
      return pbItemBall_sin_archipelago(item, quantity, item_name, canRandom)
    end
  else
    # Si AP NO está conectado, dar el ítem normalmente
    return pbItemBall_sin_archipelago(item, quantity, item_name, canRandom)
  end
end

ArchipelagoNetwork.log_archivo "Hook de pbItemBall instalado correctamente."
echoln "[Archipelago] Hook de pbItemBall instalado correctamente."

#=============================================================================
# ** Hook de pbReceiveItem — Intercepta ítems dados por NPCs o tiendas
#=============================================================================
alias pbReceiveItem_sin_archipelago pbReceiveItem unless defined?(pbReceiveItem_sin_archipelago)

def pbReceiveItem(item, quantity = 1, item_name = "", music = nil, canRandom = true)
  # Si Archipelago indica no randomizar NPCs, pasamos al nativo
  if $ArchipelagoOptions && $ArchipelagoOptions["randomize_npc_items"] == 0
    return pbReceiveItem_sin_archipelago(item, quantity, item_name, music, canRandom)
  end

  # Si el servidor nos está inyectando un ítem, pasar directamente
  if ArchipelagoNetwork.recibiendo_de_servidor
    return pbReceiveItem_sin_archipelago(item, quantity, item_name, music, canRandom)
  end

  # Si AP está conectado, bloqueamos el ítem original de NPC
  if ArchipelagoNetwork.conectado?
    begin
      item_data = GameData::Item.try_get(item)
      item_id = item_data ? item_data.id.to_s : item.to_s
      current_map = $game_map ? $game_map.map_id : 0
      event_id = 0
      if $game_system && $game_system.map_interpreter
        event_id = $game_system.map_interpreter.instance_variable_get(:@event_id) || 0
      end

      resp = ArchipelagoNetwork.enviar_evento_recibido(item_id, quantity, current_map, event_id)
      
      if resp && resp["tracked"] == true
        Kernel.pbMessage(_INTL("¡Objeto enviado a Archipelago!"))
        return true
      else
        return pbReceiveItem_sin_archipelago(item, quantity, item_name, music, canRandom)
      end
    rescue Exception => e
      ArchipelagoNetwork.log_archivo "Error en hook pbReceiveItem AP: #{e.message}"
      return pbReceiveItem_sin_archipelago(item, quantity, item_name, music, canRandom)
    end
  else
    return pbReceiveItem_sin_archipelago(item, quantity, item_name, music, canRandom)
  end
end

ArchipelagoNetwork.log_archivo "Hook de pbReceiveItem instalado correctamente."
echoln "[Archipelago] Hook de pbReceiveItem instalado correctamente."

#=============================================================================
# Intento de conexión inicial (se hará lazy al primer evento si falla aquí)
#=============================================================================
begin
  ArchipelagoNetwork.conectar
rescue Exception => e
  ArchipelagoNetwork.log_archivo "Error en conexión inicial: #{e.message}"
  echoln "[Archipelago] Error en conexión inicial: #{e.message}"
end

#=============================================================================
# Log de inicialización
#=============================================================================
ArchipelagoNetwork.log_archivo "============================================="
ArchipelagoNetwork.log_archivo " Archipelago Network Module v0.3 cargado"
ArchipelagoNetwork.log_archivo " Modo: HTTP via HTTPLite"
ArchipelagoNetwork.log_archivo " Compatible con PIF v6.7"
ArchipelagoNetwork.log_archivo "============================================="

echoln "============================================="
echoln " Archipelago Network Module v0.3 cargado"
echoln " Modo: HTTP via HTTPLite"
echoln " Compatible con PIF v6.7"
echoln "============================================="

#=============================================================================
# Inyección al Game Loop (Events.onMapUpdate)
#=============================================================================
Events.onMapUpdate += proc { |sender, e|
  ArchipelagoNetwork.procesar_eventos_servidor
  ArchipelagoNetwork.revisar_medallas
  
  # Desencolar de forma segura (fuera de combate y sin interrumpir diálogos o movimiento)
  if $game_temp && !$game_temp.message_window_showing && $game_player && !$game_player.moving?
    if ArchipelagoNetwork.items_pendientes && ArchipelagoNetwork.items_pendientes.length > 0
      item_data = ArchipelagoNetwork.items_pendientes.shift
      ArchipelagoNetwork.recibiendo_de_servidor = true
      pbReceiveItem(item_data[:item], item_data[:quantity], item_data[:name])
      ArchipelagoNetwork.recibiendo_de_servidor = false
    elsif ArchipelagoNetwork.mensajes_pendientes && ArchipelagoNetwork.mensajes_pendientes.length > 0
      msg = ArchipelagoNetwork.mensajes_pendientes.shift
      Kernel.pbMessage(_INTL(msg))
    end
  end
}

#=============================================================================
# Interceptar Pokémon de Regalo (Gift Pokémon)
#=============================================================================
alias original_pbAddPokemon pbAddPokemon unless defined?(original_pbAddPokemon)

def pbAddPokemon(pkmn, level = 1, see_form = true, dontRandomize = false, variableToSave = nil)
  if ArchipelagoNetwork.recibiendo_de_servidor
    return original_pbAddPokemon(pkmn, level, see_form, dontRandomize, variableToSave)
  end

  poke_id = pkmn.is_a?(PokeBattle_Pokemon) ? pkmn.species : pkmn
  map_id = $game_map ? $game_map.map_id : 0
  
  ArchipelagoNetwork.enviar_mensaje({
    "type" => "pokemon_received",
    "species" => poke_id.to_s,
    "map_id" => map_id
  })
  
  Kernel.pbMessage(_INTL("¡Encontraste un Pokémon que ha sido enviado a Archipelago!"))
  return true 
end

#=============================================================================
# Interceptar Intercambios (Trades)
#=============================================================================
alias original_pbStartTrade pbStartTrade unless defined?(original_pbStartTrade)

def pbStartTrade(pokemonIndex, newpoke, nickname, trainerName, trainerGender=0, savegame=false)
  if ArchipelagoNetwork.recibiendo_de_servidor
    original_pbStartTrade(pokemonIndex, newpoke, nickname, trainerName, trainerGender, savegame)
    return
  end

  $Trainer.party[pokemonIndex] = nil
  $Trainer.party.compact!
  
  map_id = $game_map ? $game_map.map_id : 0
  trade_poke_id = newpoke.is_a?(PokeBattle_Pokemon) ? newpoke.species : newpoke
  
  ArchipelagoNetwork.enviar_mensaje({
    "type" => "trade_completed",
    "species" => trade_poke_id.to_s,
    "map_id" => map_id
  })
  
  Kernel.pbMessage(_INTL("¡El Pokémon del intercambio fue enviado a la red de Archipelago!"))
end

#=============================================================================
# ** Hook de Dexsanity (Captura de Pokémon)
#=============================================================================
alias original_pbStorePokemon pbStorePokemon unless defined?(original_pbStorePokemon)

def pbStorePokemon(pkmn)
  # Si estamos recibiendo de AP, simplemente almacenarlo
  if ArchipelagoNetwork.recibiendo_de_servidor
    return original_pbStorePokemon(pkmn)
  end

  # Si Archipelago está conectado, enviamos notificación de captura
  if ArchipelagoNetwork.conectado?
    poke_id = pkmn.is_a?(PokeBattle_Pokemon) ? pkmn.species : pkmn
    map_id = $game_map ? $game_map.map_id : 0
    event_id = 0
    if $game_system && $game_system.map_interpreter
      event_id = $game_system.map_interpreter.instance_variable_get(:@event_id) || 0
    end

    ArchipelagoNetwork.enviar_mensaje({
      "type" => "pokemon_caught",
      "species" => poke_id.to_s,
      "map_id" => map_id,
      "event_id" => event_id
    })
  end

  return original_pbStorePokemon(pkmn)
end

#=============================================================================
# ** Hook de Trainersanity (Derrotar Entrenadores)
#=============================================================================
alias original_pbTrainerBattle pbTrainerBattle unless defined?(original_pbTrainerBattle)

def pbTrainerBattle(trainerID, trainerName, endSpeech=nil, doubleBattle=false, trainerPartyID=0, canLose=false, variable=nil)
  # Llamar a la batalla original
  result = original_pbTrainerBattle(trainerID, trainerName, endSpeech, doubleBattle, trainerPartyID, canLose, variable)
  
  # Si el resultado es true, ganamos la batalla
  if result == true && ArchipelagoNetwork.conectado?
    map_id = $game_map ? $game_map.map_id : 0
    event_id = 0
    if $game_system && $game_system.map_interpreter
      event_id = $game_system.map_interpreter.instance_variable_get(:@event_id) || 0
    end
    
    ArchipelagoNetwork.enviar_mensaje({
      "type" => "trainer_defeated",
      "trainer_id" => "#{trainerID}_#{trainerName}",
      "map_id" => map_id,
      "event_id" => event_id
    })
  end
  
  return result
end

#=============================================================================
# ** Hook del Goal (Victoria - Hall of Fame)
#=============================================================================
alias original_pbHallOfFameEntry pbHallOfFameEntry unless defined?(original_pbHallOfFameEntry)

def pbHallOfFameEntry(*args)
  if ArchipelagoNetwork.conectado?
    ArchipelagoNetwork.enviar_meta
  end
  return original_pbHallOfFameEntry(*args)
end

