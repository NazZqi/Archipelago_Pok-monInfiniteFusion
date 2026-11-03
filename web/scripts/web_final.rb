# Corre después de todos los scripts de PIF. Sin red, un intento de descarga falla y
# deja el sprite en "?" aunque la hoja esté en el paquete.
def downloadAllowed?
  return false
end

# empaquetar.py deja los .dat descifrados: hacerlo aquí costaba 45 s por archivo grande
module Encryption
  def self.xor(datos)
    return datos
  end
end

# La intro elige una fusión de la lista de sprites custom, que no va en el paquete
def getRandomFusionForIntro
  return PIFSprite.new(:AUTOGEN, rand(NB_POKEMON) + 1, rand(NB_POKEMON) + 1, "")
end

# empaquetar.py parte cada hoja en tiras: decodificarla entera costaba 800 ms por sprite
class AutogenExtracter
  FILAS_TIRA = 5

  def getSpritesheetPath(pif_sprite)
    tira = pif_sprite.body_id / COLUMNS / FILAS_TIRA
    return "#{SPRITESHEET_FOLDER_PATH}#{pif_sprite.head_id}/#{tira}.png"
  end

  def get_sprite_position_on_spritesheet(body_id, sprite_size, nb_column)
    x, y = super
    return x, y % (FILAS_TIRA * sprite_size)
  end
end
