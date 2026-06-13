# ExportAPLocations.rb
# Escanea todos los mapas para exportar y clasificar ubicaciones de Archipelago.

def exportar_ubicaciones_ap
  ubicaciones = []
  base_code = 2560000
  code = base_code
  
  # Buscar en todos los mapas
  (1..999).each do |map_id|
    filename = sprintf("Data/Map%03d.rxdata", map_id)
    next unless pbRgssExists?(filename)
    
    begin
      map = load_data(filename)
      next unless map && map.events
      
      map.events.values.each do |event|
        items_en_evento = 0
        
        event.pages.each do |page|
          next unless page.list
          page.list.each do |cmd|
            script_text = nil
            if cmd.code == 355 || cmd.code == 655
              script_text = cmd.parameters[0]
            elsif cmd.code == 111 && cmd.parameters[0] == 12
              script_text = cmd.parameters[1]
            end
            
            if script_text
              if script_text.include?("pbItemBall")
                ubicaciones << {
                  "id" => "#{map_id}_#{event.id}_#{items_en_evento}",
                  "map_id" => map_id,
                  "event_id" => event.id,
                  "type" => "itemball",
                  "code" => code
                }
                code += 1
                items_en_evento += 1
              elsif script_text.include?("pbReceiveItem") || script_text.include?("pbAddPokemon")
                ubicaciones << {
                  "id" => "#{map_id}_#{event.id}_#{items_en_evento}",
                  "map_id" => map_id,
                  "event_id" => event.id,
                  "type" => "npc",
                  "code" => code
                }
                code += 1
                items_en_evento += 1
              elsif script_text.include?("pbHiddenItem")
                ubicaciones << {
                  "id" => "#{map_id}_#{event.id}_#{items_en_evento}",
                  "map_id" => map_id,
                  "event_id" => event.id,
                  "type" => "hidden_item",
                  "code" => code
                }
                code += 1
                items_en_evento += 1
              end
            end
          end
        end
      end
    rescue Exception => e
      # Ignorar mapas corruptos
    end
  end
  
  # Escribir el JSON "a mano" ya que no tenemos la gema 'json' garantizada
  json_str = "[\n"
  ubicaciones.each_with_index do |ub, index|
    json_str += "  {\n"
    json_str += "    \"id\": \"#{ub['id']}\",\n"
    json_str += "    \"map_id\": #{ub['map_id']},\n"
    json_str += "    \"event_id\": #{ub['event_id']},\n"
    json_str += "    \"type\": \"#{ub['type']}\",\n"
    json_str += "    \"code\": #{ub['code']}\n"
    json_str += "  }"
    json_str += "," if index < ubicaciones.size - 1
    json_str += "\n"
  end
  json_str += "]\n"
  
  File.open("Data/ap_locations_classified.json", "w") do |f|
    f.write(json_str)
  end
  
  puts "[Archipelago] Ubicaciones exportadas: #{ubicaciones.size}"
end

# Ejecutar automáticamente la primera vez que se carga el script
if !$AP_LOCATIONS_EXPORTED
  exportar_ubicaciones_ap()
  $AP_LOCATIONS_EXPORTED = true
end
