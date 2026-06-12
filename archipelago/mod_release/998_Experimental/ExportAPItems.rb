#=============================================================================
# Script temporal para exportar GameData::Item a JSON
#=============================================================================

module APItemExporter
  @exportado = false

  def self.escape_str(str)
    str.to_s.gsub("\\", "\\\\").gsub("\"", "\\\"").gsub("\n", "\\n")
  end

  def self.hash_to_json(hash)
    pairs = hash.map do |key, value|
      k = "\"#{escape_str(key)}\""
      v = case value
          when String then "\"#{escape_str(value)}\""
          when Integer, Float then value.to_s
          when TrueClass then "true"
          when FalseClass then "false"
          when NilClass then "null"
          else "\"#{escape_str(value.to_s)}\""
          end
      "#{k}:#{v}"
    end
    "{#{pairs.join(",")}}"
  end

  def self.exportar
    return if @exportado
    output_path = "ap_items_dump.json"
    
    if File.exist?(output_path)
      @exportado = true
      return
    end

    begin
      items_json_array = []
      
      GameData::Item.list_all.each do |id, item|
        classification = "filler"
        if item.is_key_item? || item.is_HM? || item.is_important?
          classification = "progression"
        elsif item.is_TM? || item.is_evolution_stone? || item.is_fossil? || item.is_mega_stone? || item.is_apricorn?
          classification = "useful"
        elsif item.price > 2000
          classification = "useful"
        end
        
        hash = {
          "id" => id.to_s,
          "id_number" => item.id_number,
          "name" => item.real_name,
          "classification" => classification,
          "is_TM" => item.is_TM?,
          "is_HM" => item.is_HM?,
          "is_key_item" => item.is_key_item?,
          "is_berry" => item.is_berry?,
          "pocket" => item.pocket
        }
        items_json_array << hash_to_json(hash)
      end

      final_json = "[" + items_json_array.join(",") + "]"

      File.open(output_path, "w") do |f|
        f.write(final_json)
      end
      
      ArchipelagoNetwork.log_archivo "Exportados #{items_json_array.length} items a #{output_path}"
      @exportado = true
    rescue Exception => e
      ArchipelagoNetwork.log_archivo "Error exportando items: #{e.message}"
    end
  end
end

Events.onMapUpdate += proc { |_sender, _e|
  APItemExporter.exportar
}
