#=============================================================================
# ** Módulo ArchipelagoNetwork
#-----------------------------------------------------------------------------
# Módulo de comunicación HTTP para la integración de Archipelago con
# Pokémon Infinite Fusion. Se conecta a un servidor local en 127.0.0.1:5050
# y envía notificaciones de eventos del juego vía HTTPLite.
#
# Protocolo: HTTP + JSON
#   POST /event   — Enviar eventos al servidor
#   POST /resync  — Reenviar ubicaciones ya marcadas y la meta
#   POST /goal    — Avisar que se completó el juego
#   GET  /poll    — Recibir ítems/comandos del servidor (?index=N&opts=1)
#
# El estado de Archipelago se guarda en la partida ($PokemonGlobal), no en el
# cliente: si el juego se cierra sin guardar, los ítems se vuelven a pedir y
# los checks hechos sin conexión se reenvían al reconectar.
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

#=============================================================================
# Estado de Archipelago guardado en la partida
#=============================================================================
class PokemonGlobalMetadata
  attr_writer :ap_items_index, :ap_checked, :ap_pendientes, :ap_meta

  # Índice del próximo ítem de AP por entregar
  def ap_items_index; @ap_items_index ||= 0; end

  # IDs de ubicaciones AP ya marcadas (se reenvían al reconectar)
  def ap_checked; @ap_checked ||= []; end

  # Checks hechos sin conexión, en orden: [{"item","quantity","map_id","event_id"}]
  def ap_pendientes; @ap_pendientes ||= []; end

  # true tras entrar al Salón de la Fama
  def ap_meta; @ap_meta ||= false; end
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

  # Jugadores visibles: cada cuántos frames se comparte la posición (~5 veces/seg)
  MOSTRAR_JUGADORES = true
  POSICION_INTERVAL_FRAMES = 8

  # Errores consecutivos antes de avisar en el log (no desactiva el módulo:
  # los checks pendientes necesitan que se siga reintentando)
  MAX_ERRORES_CONSECUTIVOS = 5

  #---------------------------------------------------------------------------
  # Estado interno (variables de módulo)
  #---------------------------------------------------------------------------
  @conectado = false
  @listo = false             # el cliente está conectado al servidor de AP
  @ultimo_error = nil
  @ultimo_intento_conexion = 0
  @errores_consecutivos = 0
  @mensajes_enviados = 0
  @frames_desde_ultimo_poll = 0
  @recibiendo_de_servidor = false
  @medallas_conocidas = []
  @latencia = 0
  @mensajes_pendientes = []
  @items_pendientes = []     # ítems recibidos aún no entregados (en memoria)
  @ultimo_encolado = -1      # índice AP del último ítem puesto en la cola
  @global_id = nil           # partida a la que pertenece la cola
  @pausa_items = false       # no reintentar entregas hasta el próximo poll
  @frames_posicion = 0
  @jugadores_remotos = []    # [{"slot","name","map_id","x","y","dir","gender"}]

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
      @listo = false
      log_archivo "Desconectado."
      echoln "[Archipelago] Desconectado."
    end

    #=========================================================================
    # conectado?
    #-------------------------------------------------------------------------
    # Retorna true si hay una conexión activa con el cliente local.
    #=========================================================================
    def conectado?
      return @conectado
    end

    #=========================================================================
    # listo?
    #-------------------------------------------------------------------------
    # Retorna true si el cliente local además está conectado al servidor AP.
    #=========================================================================
    def listo?
      return @conectado && @listo
    end

    #=========================================================================
    # registrar_check
    #-------------------------------------------------------------------------
    # Avisa al cliente que el jugador obtuvo un ítem de un evento del mapa.
    # Retorna:
    #   :tracked   — es una ubicación AP; no entregar el ítem original
    #   :nativo    — no es ubicación AP; entregar el ítem original
    #   :pendiente — sin conexión; se guardó en la partida para reenviarlo
    #=========================================================================
    def registrar_check(tipo, item_name, cantidad, map_id, event_id)
      mensaje = {
        "type"     => tipo,
        "item"     => item_name.to_s,
        "quantity" => cantidad,
        "map_id"   => map_id,
        "event_id" => event_id
      }

      # Respetar el orden: si ya hay pendientes, este va detrás
      if $PokemonGlobal.ap_pendientes.empty?
        resultado = resultado_check(enviar_mensaje(mensaje))
        return resultado unless resultado == :pendiente
      end

      $PokemonGlobal.ap_pendientes.push(mensaje)
      log_archivo "Check guardado sin conexión: #{map_id}_#{event_id} (#{item_name})"
      return :pendiente
    end

    #=========================================================================
    # procesar_un_pendiente
    #-------------------------------------------------------------------------
    # Reenvía el check pendiente más antiguo. Llamar fuera de diálogos.
    # Retorna true si procesó uno.
    #=========================================================================
    def procesar_un_pendiente
      return false unless listo? && $PokemonGlobal && !$PokemonGlobal.ap_pendientes.empty?

      mensaje = $PokemonGlobal.ap_pendientes.first
      resultado = resultado_check(enviar_mensaje(mensaje))
      return false if resultado == :pendiente

      $PokemonGlobal.ap_pendientes.shift
      if resultado == :nativo
        # No era una ubicación de esta semilla: entregar el ítem original ahora
        item = GameData::Item.try_get(mensaje["item"])
        if item
          @recibiendo_de_servidor = true
          pbReceiveItem(item.id, mensaje["quantity"] || 1)
          @recibiendo_de_servidor = false
        end
      end
      return true
    rescue Exception => e
      @recibiendo_de_servidor = false
      log_archivo "Error procesando check pendiente: #{e.message}"
      return false
    end

    #=========================================================================
    # enviar_meta
    #-------------------------------------------------------------------------
    # Avisa al cliente de Archipelago que el juego ha sido completado.
    # La meta queda guardada en la partida y se reenvía al reconectar.
    #=========================================================================
    def enviar_meta
      $PokemonGlobal.ap_meta = true if $PokemonGlobal
      return false unless listo?

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
    # resincronizar
    #-------------------------------------------------------------------------
    # Reenvía al cliente las ubicaciones ya marcadas y la meta. Se llama cada
    # vez que el cliente pasa a estar conectado al servidor AP.
    #=========================================================================
    def resincronizar
      return unless $PokemonGlobal
      ok = enviar_post("/resync", {
        "locations" => $PokemonGlobal.ap_checked,
        "goal"      => $PokemonGlobal.ap_meta
      })
      log_archivo "Resincronización: #{$PokemonGlobal.ap_checked.size} ubicaciones, meta=#{$PokemonGlobal.ap_meta} (#{ok ? 'ok' : 'falló'})"
    end

    #=========================================================================
    # siguiente_indice
    #-------------------------------------------------------------------------
    # Próximo índice de ítem AP que hay que pedir al cliente.
    #=========================================================================
    def siguiente_indice
      # Al cargar otra partida, la cola en memoria ya no aplica
      if @global_id != $PokemonGlobal.object_id
        @global_id = $PokemonGlobal.object_id
        @items_pendientes = []
        @ultimo_encolado = -1
      end
      return [$PokemonGlobal.ap_items_index, @ultimo_encolado + 1].max
    end

    #=========================================================================
    # poll_servidor
    #-------------------------------------------------------------------------
    # Lee datos del servidor via HTTP GET (no-bloqueante, con rate limiting).
    # Retorna: Hash con datos recibidos, o nil si no hay nada.
    #=========================================================================
    def poll_servidor
      return nil unless $PokemonGlobal

      # Intentar reconectar automáticamente si no está conectado
      conectar unless conectado?
      return nil unless conectado?

      # Rate limiting por frames
      @frames_desde_ultimo_poll += 1
      return nil if @frames_desde_ultimo_poll < POLL_INTERVAL_FRAMES
      @frames_desde_ultimo_poll = 0
      @pausa_items = false

      begin
        url = BASE_URL + "/poll?index=#{siguiente_indice}"
        url += "&opts=1" if $ArchipelagoOptions.nil?

        start_time = Time.now
        response = HTTPLite.get(url)
        @latencia = ((Time.now - start_time) * 1000).to_i

        if response.is_a?(Hash) && response[:status] == 200
          data = HTTPLite::JSON.parse(response[:body])

          estaba_listo = @listo
          @listo = (data["ready"] == true)
          resincronizar if @listo && !estaba_listo

          events = data["events"]
          if events && events.is_a?(Array) && events.size > 0
            log_archivo "Recibidos #{events.size} eventos del servidor"
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

        elsif evento.has_key?("index")
          # Ítem recibido (give_item / give_badge / unknown). Se encola en orden y
          # el índice guardado solo avanza al entregarlo de verdad.
          index = evento["index"].to_i
          next if index < siguiente_indice
          @items_pendientes.push(evento)
          @ultimo_encolado = index

        elsif action == "chat_message"
          msg = evento["text"] || ""
          @mensajes_pendientes.push(msg) if msg.length > 0
        end
      end
    rescue Exception => e
      log_archivo "Error procesando eventos: #{e.message}"
    end

    #=========================================================================
    # entregar_siguiente_item
    #-------------------------------------------------------------------------
    # Entrega el próximo ítem de la cola. Llamar fuera de diálogos.
    # Retorna true si entregó uno.
    #=========================================================================
    def entregar_siguiente_item
      return false if @pausa_items || @items_pendientes.empty?

      evento = @items_pendientes.first
      index = evento["index"].to_i
      if index != $PokemonGlobal.ap_items_index
        # Hueco en la secuencia (no debería pasar): rehacer la cola desde el índice guardado
        log_archivo "Índice inesperado #{index} (esperado #{$PokemonGlobal.ap_items_index}); se vuelve a pedir."
        @items_pendientes = []
        @ultimo_encolado = $PokemonGlobal.ap_items_index - 1
        return false
      end

      entregado = true
      case evento["action"]
      when "give_item"
        item_obj = GameData::Item.try_get(evento["item"])
        if item_obj
          log_archivo "Entregando ítem de AP ##{index}: #{item_obj.id}"
          @recibiendo_de_servidor = true
          entregado = pbReceiveItem(item_obj.id, (evento["quantity"] || 1).to_i)
          @recibiendo_de_servidor = false
        else
          log_archivo "Ítem desconocido del servidor: #{evento['item']}"
          @mensajes_pendientes.push("¡Recibiste un objeto misterioso de AP! (#{evento['item']})")
        end
      when "give_badge"
        badge_id = (evento["badge_id"] || 0).to_i
        if $Trainer && $Trainer.badges
          $Trainer.badges[badge_id] = true
          @medallas_conocidas[badge_id] = true
          @mensajes_pendientes.push("¡Has recibido #{evento['name'] || "Medalla #{badge_id}"} de Archipelago!")
        end
      else
        @mensajes_pendientes.push("¡Recibiste un objeto misterioso de AP! (#{evento['name']})")
      end

      if entregado == false
        # Mochila llena u otro rechazo: reintentar tras el próximo poll
        @pausa_items = true
        return false
      end

      @items_pendientes.shift
      $PokemonGlobal.ap_items_index = index + 1
      return true
    rescue Exception => e
      @recibiendo_de_servidor = false
      @pausa_items = true
      log_archivo "Error entregando ítem de AP: #{e.message}"
      return false
    end

    #=========================================================================
    # actualizar_posicion
    #-------------------------------------------------------------------------
    # Comparte la posición propia y recibe la de los demás jugadores de este
    # juego en la sala. Llamar cada frame; actúa cada POSICION_INTERVAL_FRAMES.
    #=========================================================================
    def actualizar_posicion
      return unless MOSTRAR_JUGADORES
      @frames_posicion += 1
      return if @frames_posicion < POSICION_INTERVAL_FRAMES
      @frames_posicion = 0

      unless listo? && $game_player && $game_map
        @jugadores_remotos = []
        return
      end

      femenino = (isPlayerFemale() rescue false)
      resp = enviar_post("/position", {
        "type"   => "position",
        "map_id" => $game_map.map_id,
        "x"      => $game_player.x,
        "y"      => $game_player.y,
        "dir"    => $game_player.direction,
        "gender" => femenino ? "f" : "m"
      })
      players = resp.is_a?(Hash) ? resp["players"] : nil
      @jugadores_remotos = players.is_a?(Array) ? players : []
    rescue Exception => e
      @jugadores_remotos = []
      log_archivo "Error compartiendo posición: #{e.message}"
    end

    #=========================================================================
    # jugadores_en_mapa
    #-------------------------------------------------------------------------
    # Jugadores remotos que están en el mapa indicado.
    #=========================================================================
    def jugadores_en_mapa(map_id)
      return @jugadores_remotos.select { |j| j.is_a?(Hash) && j["map_id"] == map_id }
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
        listo: listo?,
        errores_consecutivos: @errores_consecutivos,
        ultimo_error: @ultimo_error,
        mensajes_enviados: @mensajes_enviados,
        checks_pendientes: $PokemonGlobal ? $PokemonGlobal.ap_pendientes.size : 0,
        items_en_cola: @items_pendientes.size
      }
    end

    #=========================================================================
    # reactivar
    #-------------------------------------------------------------------------
    # Fuerza un intento de reconexión inmediato.
    #=========================================================================
    def reactivar
      @errores_consecutivos = 0
      @ultimo_intento_conexion = 0
      log_archivo "Módulo reactivado. Se intentará reconectar."
      echoln "[Archipelago] Módulo reactivado. Se intentará reconectar."
    end

    private

    #=========================================================================
    # resultado_check (interno)
    #-------------------------------------------------------------------------
    # Traduce la respuesta del cliente a :tracked, :nativo o :pendiente.
    #=========================================================================
    def resultado_check(resp)
      return :pendiente unless resp.is_a?(Hash) && resp.has_key?("tracked")
      if resp["tracked"] == true
        location = resp["location"]
        $PokemonGlobal.ap_checked.push(location) if location && !$PokemonGlobal.ap_checked.include?(location)
        return :tracked
      end
      return :nativo
    end

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

      return enviar_post("/event", mensaje_hash)
    end

    #=========================================================================
    # enviar_post (interno)
    #-------------------------------------------------------------------------
    # Envía datos al servidor via HTTP POST. Retorna el JSON de respuesta o false.
    #=========================================================================
    def enviar_post(ruta, mensaje_hash)
      begin
        body = hash_to_json(mensaje_hash)

        response = HTTPLite.post_body(
          BASE_URL + ruta,
          body,
          "application/json"
        )

        if response.is_a?(Hash) && response[:status] == 200
          @mensajes_enviados += 1
          @errores_consecutivos = 0

          tipo = mensaje_hash["type"] || ruta
          # La posición se envía ~5 veces por segundo: no llenar el log
          if tipo != "heartbeat" && tipo != "position"
            log_archivo "Enviado: #{tipo} — #{body}"
            echoln "[Archipelago] Enviado: #{tipo}"
          end

          parsed = HTTPLite::JSON.parse(response[:body]) rescue {}
          # El cliente perdió el servidor AP: dejar de considerarlo listo
          @listo = false if parsed.is_a?(Hash) && parsed["status"] == "offline"
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
    # Incrementa el contador de errores y avisa en el log al llegar al máximo.
    #=========================================================================
    def registrar_error
      @errores_consecutivos += 1
      if @errores_consecutivos == MAX_ERRORES_CONSECUTIVOS
        log_archivo "#{MAX_ERRORES_CONSECUTIVOS} errores consecutivos. ¿Está abierto el cliente de Archipelago?"
        echoln "[Archipelago] #{MAX_ERRORES_CONSECUTIVOS} errores consecutivos. ¿Está abierto el cliente?"
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
        "\"#{escape_json_string(key.to_s)}\":#{valor_json(value)}"
      end
      "{#{pairs.join(",")}}"
    end

    def valor_json(value)
      case value
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
      when Array
        "[#{value.map { |v| valor_json(v) }.join(",")}]"
      when Hash
        hash_to_json(value)
      else
        "\"#{escape_json_string(value.to_s)}\""
      end
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
# Helpers de los hooks
#=============================================================================
def ap_evento_actual
  current_map = $game_map ? $game_map.map_id : 0
  event_id = 0
  if $game_system && $game_system.map_interpreter
    event_id = $game_system.map_interpreter.instance_variable_get(:@event_id) || 0
  end
  return current_map, event_id
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

  begin
    current_map, event_id = ap_evento_actual

    # Resolver el nombre real del ítem para el log
    item_data = GameData::Item.try_get(item)
    item_id = item_data ? item_data.id.to_s : item.to_s

    resultado = ArchipelagoNetwork.registrar_check("item_found", item_id, quantity, current_map, event_id)
    return pbItemBall_sin_archipelago(item, quantity, item_name, canRandom) if resultado == :nativo

    if resultado == :tracked
      pbSEPlay("Pokemon get")
      Kernel.pbMessage(_INTL("\\se[Pokemon get]¡Encontraste un objeto para Archipelago!"))
    else
      Kernel.pbMessage(_INTL("Sin conexión con Archipelago. El objeto se enviará al reconectar."))
    end

    # Desaparecer el evento del mapa (la Pokéball visual)
    if event_id > 0
      $game_self_switches[[current_map, event_id, "A"]] = true
      $game_map.need_refresh = true
    end
    return true
  rescue Exception => e
    ArchipelagoNetwork.log_archivo "Error en hook pbItemBall AP: #{e.message}"
    # Fallback: dar el ítem normal si algo falla
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

  begin
    item_data = GameData::Item.try_get(item)
    item_id = item_data ? item_data.id.to_s : item.to_s
    current_map, event_id = ap_evento_actual

    resultado = ArchipelagoNetwork.registrar_check("item_received", item_id, quantity, current_map, event_id)
    case resultado
    when :tracked
      Kernel.pbMessage(_INTL("¡Objeto enviado a Archipelago!"))
      return true
    when :pendiente
      Kernel.pbMessage(_INTL("Sin conexión con Archipelago. El objeto se enviará al reconectar."))
      return true
    else
      return pbReceiveItem_sin_archipelago(item, quantity, item_name, music, canRandom)
    end
  rescue Exception => e
    ArchipelagoNetwork.log_archivo "Error en hook pbReceiveItem AP: #{e.message}"
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
ArchipelagoNetwork.log_archivo " Archipelago Network Module v0.4 cargado"
ArchipelagoNetwork.log_archivo " Modo: HTTP via HTTPLite"
ArchipelagoNetwork.log_archivo " Compatible con PIF v6.7"
ArchipelagoNetwork.log_archivo "============================================="

echoln "============================================="
echoln " Archipelago Network Module v0.4 cargado"
echoln " Modo: HTTP via HTTPLite"
echoln " Compatible con PIF v6.7"
echoln "============================================="

#=============================================================================
# Inyección al Game Loop (Events.onMapUpdate)
#=============================================================================
Events.onMapUpdate += proc { |sender, e|
  ArchipelagoNetwork.procesar_eventos_servidor
  ArchipelagoNetwork.revisar_medallas
  ArchipelagoNetwork.actualizar_posicion

  # Desencolar de forma segura (fuera de combate y sin interrumpir diálogos o movimiento).
  # Una acción por frame: checks pendientes, luego ítems recibidos, luego mensajes.
  if $game_temp && !$game_temp.message_window_showing && $game_player && !$game_player.moving?
    if ArchipelagoNetwork.procesar_un_pendiente
      # nada más este frame
    elsif ArchipelagoNetwork.entregar_siguiente_item
      # nada más este frame
    elsif ArchipelagoNetwork.mensajes_pendientes && ArchipelagoNetwork.mensajes_pendientes.length > 0
      msg = ArchipelagoNetwork.mensajes_pendientes.shift
      Kernel.pbMessage(_INTL(msg))
    end
  end
}

#=============================================================================
# ** Hook del Goal (Victoria - Hall of Fame)
#=============================================================================
alias original_pbHallOfFameEntry pbHallOfFameEntry unless defined?(original_pbHallOfFameEntry)

def pbHallOfFameEntry(*args)
  # Guarda la meta en la partida aunque no haya conexión; se reenvía al reconectar
  ArchipelagoNetwork.enviar_meta
  return original_pbHallOfFameEntry(*args)
end
