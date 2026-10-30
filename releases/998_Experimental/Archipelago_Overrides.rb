# ==============================================================================
# Archipelago Overrides
# ==============================================================================
# Este archivo contiene las inyecciones de código (hooks) necesarias para
# conectar Archipelago con Pokémon Infinite Fusion sin modificar los scripts
# originales del juego base. Esto asegura compatibilidad con actualizaciones.
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Overrides para el HUD (005_Sprites/007_Spriteset_Map.rb)
# ------------------------------------------------------------------------------

class Spriteset_Map
  alias ap_original_initialize initialize
  def initialize(map=nil)
    ap_original_initialize(map)
    # Crear el sprite del HUD de Archipelago
    @ap_sprite = Sprite.new(@@viewport3)
    @ap_sprite.z = 99999
    @ap_sprite.bitmap = Bitmap.new(150, 32)
    @ap_sprite.x = Graphics.width - 150
    @ap_sprite.y = 10
  end

  alias ap_original_dispose dispose
  def dispose
    ap_original_dispose
    # Limpiar el sprite
    @ap_sprite.dispose if @ap_sprite
    @ap_sprite = nil
    ap_dispose_remotos if respond_to?(:ap_dispose_remotos)
  end

  alias ap_original_update update
  def update
    ap_original_update
    # Jugadores de la misma sala (ArchipelagoRemotePlayers.rb)
    ap_actualizar_remotos if respond_to?(:ap_actualizar_remotos)
    # Actualizar el HUD en cada frame
    if defined?(ArchipelagoNetwork) && @ap_sprite && @ap_sprite.bitmap
      @ap_sprite.bitmap.clear
      estado = ArchipelagoNetwork.estado
      latencia = ArchipelagoNetwork.latencia || 0
      
      pbSetSystemFont(@ap_sprite.bitmap)
      
      pendientes = estado[:checks_pendientes] > 0 ? " (#{estado[:checks_pendientes]})" : ""
      if estado[:listo]
        @ap_sprite.bitmap.fill_rect(0, 8, 10, 10, Color.new(0, 255, 0)) # Círculo Verde
        pbDrawTextPositions(@ap_sprite.bitmap, [[ "AP: #{latencia}ms#{pendientes}", 15, -4, 0, Color.new(255,255,255), Color.new(0,0,0) ]])
      elsif estado[:semilla_distinta]
        @ap_sprite.bitmap.fill_rect(0, 8, 10, 10, Color.new(255, 0, 0)) # Círculo Rojo
        pbDrawTextPositions(@ap_sprite.bitmap, [[ "AP: Otra semilla", 15, -4, 0, Color.new(255,100,100), Color.new(0,0,0) ]])
      elsif estado[:conectado]
        # Cliente abierto pero sin servidor AP: los checks quedan pendientes
        @ap_sprite.bitmap.fill_rect(0, 8, 10, 10, Color.new(255, 200, 0)) # Círculo Amarillo
        pbDrawTextPositions(@ap_sprite.bitmap, [[ "AP: Sin servidor#{pendientes}", 15, -4, 0, Color.new(255,220,100), Color.new(0,0,0) ]])
      else
        @ap_sprite.bitmap.fill_rect(0, 8, 10, 10, Color.new(255, 0, 0)) # Círculo Rojo
        pbDrawTextPositions(@ap_sprite.bitmap, [[ "AP: Desc", 15, -4, 0, Color.new(255,100,100), Color.new(0,0,0) ]])
      end
    end
  end
end
