# ==============================================================================
# Archipelago Overrides
# ==============================================================================
# Este archivo contiene las inyecciones de código (hooks) necesarias para
# conectar Archipelago con Pokémon Infinite Fusion sin modificar los scripts
# originales del juego base. Esto asegura compatibilidad con actualizaciones.
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Overrides para Bayas (012_Overworld/006_Overworld_BerryPlants.rb)
# ------------------------------------------------------------------------------

alias ap_original_pbPickBerry pbPickBerry
def pbPickBerry(berry, qty = 1)
  if Object.const_defined?(:ArchipelagoNetwork) && ArchipelagoNetwork.conectado?
    interp = pbMapInterpreter
    thisEvent = interp.get_character(0)
    berryData = interp.getVariable
    item = GameData::Item.get(berry)
    itemname = (qty > 1) ? item.name_plural : item.name
    message = (qty > 1) ? _INTL("There are {1} \\c[1]{2}\\c[0]!\nWant to pick them?", qty, itemname) : _INTL("There is 1 \\c[1]{1}\\c[0]!\nWant to pick it?", itemname)
    
    if pbConfirmMessage(message)
      ArchipelagoNetwork.enviar_ubicacion("BERRY", qty, $game_map.map_id, interp.instance_variable_get(:@event_id))
      pbMEPlay("Berry Obtained")
      pbMessage(_INTL("¡Encontraste un objeto para Archipelago!"))
      if Settings::NEW_BERRY_PLANTS
        pbMessage(_INTL("The soil returned to its soft and earthy state."))
        berryData = [0, nil, 0, 0, 0, 0, 0, 0]
      else
        pbMessage(_INTL("The soil returned to its soft and loamy state."))
        berryData = [0, nil, false, 0, 0, 0]
      end
      interp.setVariable(berryData)
      pbSetSelfSwitch(thisEvent.id, "A", true)
    end
    return
  end
  # Si no está conectado a AP, ejecuta el comportamiento original
  ap_original_pbPickBerry(berry, qty)
end

alias ap_original_pbBerryPlant pbBerryPlant
def pbBerryPlant
  interp = pbMapInterpreter
  berryData = interp.getVariable
  
  # Si la baya está en la fase final (lista para recoger) y AP está conectado, interceptamos.
  if berryData && berryData[0] == 5 && Object.const_defined?(:ArchipelagoNetwork) && ArchipelagoNetwork.conectado?
    thisEvent = interp.get_character(0)
    berry = berryData[1]
    berryvalues = GameData::BerryPlant.get(berry)
    
    # Calcular cantidad (lógica original)
    berrycount = 1
    if berryData.length > 6
      berrycount = [berryvalues.maximum_yield - berryData[6], berryvalues.minimum_yield].max
    else
      if berryData[4] > 0
        berrycount = (berryvalues.maximum_yield - berryvalues.minimum_yield) * (berryData[4] - 1)
        berrycount += rand(1 + berryvalues.maximum_yield - berryvalues.minimum_yield)
        berrycount = (berrycount / 4) + berryvalues.minimum_yield
      else
        berrycount = berryvalues.minimum_yield
      end
    end
    
    item = GameData::Item.get(berry)
    itemname = (berrycount > 1) ? item.name_plural : item.name
    message = (berrycount > 1) ? _INTL("There are {1} \\c[1]{2}\\c[0]!\nWant to pick them?", berrycount, itemname) : _INTL("There is 1 \\c[1]{1}\\c[0]!\nWant to pick it?", itemname)
    
    # Detener animación del evento temporalmente
    thisEvent.turn_up
    
    if pbConfirmMessage(message)
      ArchipelagoNetwork.enviar_ubicacion("BERRY", berrycount, $game_map.map_id, interp.instance_variable_get(:@event_id))
      pbMEPlay("Berry Obtained")
      pbMessage(_INTL("¡Encontraste un objeto para Archipelago!"))
      if Settings::NEW_BERRY_PLANTS
        pbMessage(_INTL("The soil returned to its soft and earthy state."))
        berryData = [0, nil, 0, 0, 0, 0, 0, 0]
      else
        pbMessage(_INTL("The soil returned to its soft and loamy state."))
        berryData = [0, nil, false, 0, 0, 0]
      end
      interp.setVariable(berryData)
    end
    return
  end
  
  # Si no aplica, ejecuta el comportamiento original para regar, plantar, etc.
  ap_original_pbBerryPlant
end

# ------------------------------------------------------------------------------
# 2. Overrides para el HUD (005_Sprites/007_Spriteset_Map.rb)
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
  end

  alias ap_original_update update
  def update
    ap_original_update
    # Actualizar el HUD en cada frame
    if defined?(ArchipelagoNetwork) && @ap_sprite && @ap_sprite.bitmap
      @ap_sprite.bitmap.clear
      estado = ArchipelagoNetwork.estado
      latencia = ArchipelagoNetwork.latencia || 0
      
      pbSetSystemFont(@ap_sprite.bitmap)
      
      if estado[:conectado]
        @ap_sprite.bitmap.fill_rect(0, 8, 10, 10, Color.new(0, 255, 0)) # Círculo Verde
        pbDrawTextPositions(@ap_sprite.bitmap, [[ "AP: #{latencia}ms", 15, -4, 0, Color.new(255,255,255), Color.new(0,0,0) ]])
      else
        @ap_sprite.bitmap.fill_rect(0, 8, 10, 10, Color.new(255, 0, 0)) # Círculo Rojo
        pbDrawTextPositions(@ap_sprite.bitmap, [[ "AP: Desc", 15, -4, 0, Color.new(255,100,100), Color.new(0,0,0) ]])
      end
    end
  end
end
