# Jugadores visibles en la versión web. juego.js retransmite por el servidor (/api/red): deja
# en red_entrada.txt a los demás y manda lo que este script escribe en red_salida.txt.
# Los dibuja ArchipelagoRemotePlayers.rb del mod de Archipelago, que empaquetar.py copia
# antes de este archivo; aquí va lo mínimo de ArchipelagoNetwork que ese archivo usa.
module ArchipelagoNetwork
  CADA_FRAMES = 15  # unas 3 veces por segundo
  LATIDO = 5        # segundos: el servidor olvida una posición a los 30 s
  @jugadores = []
  @frames = 0
  @ultima = nil
  @enviada = Time.at(0)

  class << self
    def jugadores_en_mapa(map_id)
      @jugadores.select { |j| j["map_id"] == map_id }
    end

    def log_archivo(texto)
      STDERR.puts("[web-red] #{texto}")
    end

    def actualizar_red
      @frames += 1
      return if @frames % CADA_FRAMES != 0
      leer_entrada
      escribir_salida if $game_player && $game_map
      WebEquipo.atender
    rescue StandardError => e
      log_archivo("#{e.class}: #{e.message}")
    end

    private

    def ruta(nombre)
      File.join(System.data_directory, nombre)
    end

    # Una línea por jugador: slot, mapa, x, y, dirección, género y nombre, separados por tab
    def leer_entrada
      archivo = ruta("red_entrada.txt")
      return @jugadores = [] unless File.exist?(archivo)
      @jugadores = File.read(archivo).split("\n").filter_map do |linea|
        slot, map_id, x, y, dir, genero, nombre = linea.split("\t", 7)
        next unless nombre
        { "slot" => slot, "map_id" => map_id.to_i, "x" => x.to_i, "y" => y.to_i,
          "dir" => dir.to_i, "gender" => genero, "name" => nombre }
      end
    end

    def escribir_salida
      genero = (isPlayerFemale() rescue false) ? "f" : "m"
      posicion = [$game_map.map_id, $game_player.x, $game_player.y, $game_player.direction, genero].join(" ")
      return if posicion == @ultima && Time.now - @enviada < LATIDO
      File.write(ruta("red_salida.txt"), posicion)
      @ultima = posicion
      @enviada = Time.now
    end
  end
end

# Los mismos ganchos que Archipelago_Overrides.rb
class Spriteset_Map
  alias web_red_update update
  def update
    web_red_update
    ap_actualizar_remotos
  end

  alias web_red_dispose dispose
  def dispose
    ap_dispose_remotos
    web_red_dispose
  end
end

Events.onMapUpdate += proc { ArchipelagoNetwork.actualizar_red }
