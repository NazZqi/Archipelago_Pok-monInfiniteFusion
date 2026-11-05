# Corre dentro del juego (web_cmd.rb de un paquete --diagnostico): deja en System.data_directory
# textos.tsv con todos los textos de messages.dat, una línea por texto:
#   sección <tab> clave <tab> original
# La sección es "M<mapa>" para los eventos de mapa o el número de MessageTypes. La clave es el
# id en las secciones de arreglo y "h:<clave>" en las de hash. Los saltos y tabs van escapados
# con Messages.normalizeValue, el mismo formato que usa Essentials al extraer traducciones.
m = Messages.new("Data/messages.dat").messages
n = ->(s) { Messages.normalizeValue(s.to_s.dup) }  # normalizeValue usa clone: con un string congelado falla
lineas = []
m[0].each_with_index do |h, mapa|
  next unless h.is_a?(Hash)
  h.each { |k, v| lineas << ["M#{mapa}", "h:" + n.(k), n.(v)].join("\t") unless v.to_s.empty? }
end
(1...m.length).each do |t|
  x = m[t]
  if x.is_a?(Array)
    x.each_with_index { |v, id| lineas << [t, id, n.(v)].join("\t") if v.is_a?(String) && !v.empty? }
  elsif x.is_a?(Hash)
    x.each { |k, v| lineas << [t, "h:" + n.(k), n.(v)].join("\t") unless v.to_s.empty? }
  end
end
File.write(File.join(System.data_directory, "textos.tsv"), lineas.join("\n"))
lineas.size
