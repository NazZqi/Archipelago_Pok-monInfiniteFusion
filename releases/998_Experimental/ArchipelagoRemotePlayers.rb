#=============================================================================
# ** Jugadores remotos de Archipelago (prototipo)
#-----------------------------------------------------------------------------
# Muestra en el mapa a los demás jugadores de Pokémon Infinite Fusion de la
# misma sala. Solo son visibles: no colisionan ni se puede interactuar.
#
# No se usa Sprite_Character porque varias extensiones de PIF asumen que el
# personaje es un Game_Event (sombras, iconos de misiones, rivales).
#=============================================================================

#=============================================================================
# Personaje sin eventos de juego: solo interpola su posición y animación.
#=============================================================================
class Game_RemotePlayer < Game_Character
  # Más de esta distancia en casillas se trata como teletransporte
  DISTANCIA_TELETRANSPORTE = 4

  def initialize(map)
    super(map)
    @through = true
    self.move_speed = 4  # algo más rápido que caminar, para alcanzar la posición
  end

  def colocar(x, y, dir, forzar = false)
    @direction = dir if [2, 4, 6, 8].include?(dir)
    return if x == @x && y == @y && !forzar
    lejos = (x - @x).abs + (y - @y).abs > DISTANCIA_TELETRANSPORTE
    @x = x
    @y = y
    if forzar || lejos
      @real_x = x * Game_Map::REAL_RES_X
      @real_y = y * Game_Map::REAL_RES_Y
    end
  end

  # Versión de Game_Character#update_move sin disparar eventos de pasos
  def update
    @moved_last_frame = @moved_this_frame
    if moving?
      distance = move_speed_real
      dest_x = @x * Game_Map::REAL_RES_X
      dest_y = @y * Game_Map::REAL_RES_Y
      @real_x = (@real_x < dest_x) ? [@real_x + distance, dest_x].min : [@real_x - distance, dest_x].max
      @real_y = (@real_y < dest_y) ? [@real_y + distance, dest_y].min : [@real_y - distance, dest_y].max
      @anime_count += 1
      @moved_this_frame = true
    else
      @moved_this_frame = false
    end
    update_pattern
  end
end

#=============================================================================
# Sprite del jugador remoto: charset de 4x4 y nombre encima.
#=============================================================================
class Sprite_RemotePlayer
  CHARSETS = {
    "m" => "Graphics/Characters/trainer_POKEMONTRAINER_Red",
    "f" => "Graphics/Characters/trainer_POKEMONTRAINER_Leaf"
  }

  attr_reader :personaje

  def initialize(viewport, personaje, nombre, genero)
    @personaje = personaje
    @sprite = Sprite.new(viewport)
    @sprite.bitmap = Bitmap.new(CHARSETS[genero] || CHARSETS["m"])
    @frame_w = @sprite.bitmap.width / 4
    @frame_h = @sprite.bitmap.height / 4
    @sprite.ox = @frame_w / 2
    @sprite.oy = @frame_h

    @etiqueta = Sprite.new(viewport)
    @etiqueta.bitmap = Bitmap.new(128, 20)
    pbSetSmallFont(@etiqueta.bitmap) rescue nil
    @etiqueta.bitmap.font.color = Color.new(255, 255, 255)
    @etiqueta.bitmap.draw_text(0, 0, 128, 20, nombre.to_s, 1)
    @etiqueta.ox = 64
    @etiqueta.oy = 20
    update
  end

  def update
    fila = (@personaje.direction / 2) - 1
    @sprite.src_rect.set(@personaje.pattern * @frame_w, fila * @frame_h, @frame_w, @frame_h)
    @sprite.x = @personaje.screen_x
    @sprite.y = @personaje.screen_y
    @sprite.z = @personaje.screen_z(@frame_h)
    @etiqueta.x = @sprite.x
    @etiqueta.y = @sprite.y - @frame_h
    @etiqueta.z = @sprite.z + 1
  end

  def dispose
    [@sprite, @etiqueta].each do |s|
      s.bitmap.dispose if s.bitmap
      s.dispose
    end
  end
end

#=============================================================================
# Integración con Spriteset_Map: cada spriteset dibuja a los jugadores que
# están en su mapa (incluye mapas vecinos visibles).
#=============================================================================
class Spriteset_Map
  def ap_actualizar_remotos
    @ap_remotos ||= {}
    datos = {}
    ArchipelagoNetwork.jugadores_en_mapa(@map.map_id).each { |j| datos[j["slot"]] = j }

    # Quitar a quien ya no está en este mapa
    (@ap_remotos.keys - datos.keys).each { |slot| @ap_remotos.delete(slot).dispose }

    datos.each do |slot, j|
      sprite = @ap_remotos[slot]
      if !sprite
        personaje = Game_RemotePlayer.new(@map)
        personaje.colocar(j["x"].to_i, j["y"].to_i, j["dir"].to_i, true)
        sprite = @ap_remotos[slot] = Sprite_RemotePlayer.new(@@viewport1, personaje, j["name"], j["gender"])
      end
      sprite.personaje.colocar(j["x"].to_i, j["y"].to_i, j["dir"].to_i)
      sprite.personaje.update
      sprite.update
    end
  rescue Exception => e
    ArchipelagoNetwork.log_archivo "Error dibujando jugadores remotos: #{e.message}"
  end

  def ap_dispose_remotos
    (@ap_remotos || {}).each_value(&:dispose)
    @ap_remotos = {}
  end
end
