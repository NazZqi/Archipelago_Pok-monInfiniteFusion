# Corre dentro del juego (web_cmd.rb de un paquete --diagnostico) con traducciones.tsv en
# System.data_directory, que sale de traducir.py armar: "original <tab> español" con el formato de
# Messages.normalizeValue. Deja spanish.dat en la misma carpeta, con la forma de messages.dat:
# mapas y secciones de hash con la misma clave, secciones de arreglo con el mismo id. Lo que no
# está traducido queda vacío o con el original: el juego cae al texto de messages.dat.
dir = System.data_directory
tr = {}
File.read(File.join(dir, "traducciones.tsv")).split("\n").each do |l|
  o, e = l.split("\t", 2)
  tr[o] = Messages.denormalizeValue(e.dup) if e && !e.empty?
end
n = ->(s) { Messages.normalizeValue(s.to_s.dup) }
traducir = lambda do |h|
  nuevo = OrderedHash.new
  h.each { |k, v| nuevo[k] = tr[n.(v)] || v }
  nuevo
end
m = Messages.new("Data/messages.dat").messages
es = []
es[0] = m[0].map { |h| h.is_a?(Hash) ? traducir.(h) : h }
(1...m.length).each do |t|
  x = m[t]
  es[t] = if x.is_a?(Array)
            x.map { |v| v.is_a?(String) && !v.empty? ? (tr[n.(v)] || "") : v }
          elsif x.is_a?(Hash)
            traducir.(x)
          else
            x
          end
end
File.binwrite(File.join(dir, "spanish.dat"), Marshal.dump(es))
[tr.size, File.size(File.join(dir, "spanish.dat"))]
