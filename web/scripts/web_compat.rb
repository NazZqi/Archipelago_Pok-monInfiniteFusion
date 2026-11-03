# Compatibilidad para correr Infinite Fusion en el core web de mkxp-z.
# PIF nativo usa Ruby 3.1 y HTTPLite; el core web usa Ruby 3.3 y no trae red.
# empaquetar.py lo antepone a 001_Settings.rb, el primer script que carga PIF.

# El pathCache del core lee cada archivo del paquete al arrancar: casi 2 minutos con OPFS.
# Sin él las rutas distinguen mayúsculas, y PIF no las respeta (Graphics/titles, eqi...).
# Esta tabla, generada por empaquetar.py, resuelve lo mismo sin tocar el disco.
module WebRutas
  @tabla = {}
  File.read("Data/web_rutas.txt").each_line(chomp: true) do |real|
    @tabla[real.downcase] = real
    sin_extension = real.sub(/\.[^.\/]*\z/, "")
    @tabla[sin_extension.downcase] ||= sin_extension
  end

  def self.real(ruta)
    return ruta unless ruta.is_a?(String)
    return @tabla[ruta.sub(/\A\.\//, "").tr("\\", "/").downcase] || ruta
  end
end

class Bitmap
  alias_method :__web_initialize, :initialize

  def initialize(*args)
    args[0] = WebRutas.real(args[0]) if args.size == 1
    __web_initialize(*args)
  end
end

[[Audio, [:bgm_play, :bgs_play, :me_play, :se_play]], [FileTest, [:exist?]], [File, [:exist?, :open]]].each do |modulo, nombres|
  nombres.each do |nombre|
    next unless modulo.respond_to?(nombre)
    original = modulo.method(nombre)
    modulo.define_singleton_method(nombre) { |ruta, *resto, **opciones, &bloque| original.call(WebRutas.real(ruta), *resto, **opciones, &bloque) }
  end
end

# El load_data del core deserializa desde el archivo abierto: 51 s para las animaciones
# de combate, contra 12 s para un archivo más del doble de grande leído entero.
module Kernel
  def load_data(ruta)
    return Marshal.load(File.open(ruta, "rb") { |f| f.read })
  end
end

# En RGSS1 el core deja `caller` sin argumentos y PIF lo llama con un rango.
# El +1 descuenta el marco de este envoltorio.
if Kernel.respond_to?(:_mkxp_kernel_caller_alias)
  module Kernel
    def caller(inicio = 1, largo = nil)
      return Kernel._mkxp_kernel_caller_alias((inicio.begin + 1)..(inicio.end + 1)) if inicio.is_a?(Range)
      return Kernel._mkxp_kernel_caller_alias(inicio + 1, largo) if largo
      return Kernel._mkxp_kernel_caller_alias(inicio + 1)
    end
    module_function :caller
  end
end

# En RGSS1 el core solo acepta scancodes numéricos en triggerex? y similares: los
# símbolos dan siempre falso (:RETURN, :ESCAPE...). Además descarta el carácter de
# cada tecla, así que Input.gets queda vacío. Se traducen símbolos y se reconstruye el texto.
module Input
  ESCANCODES_WEB = {
    :RETURN => 40, :ESCAPE => 41, :BACKSPACE => 42, :TAB => 43, :SPACE => 44,
    :RIGHT => 79, :LEFT => 80, :DOWN => 81, :UP => 82, :INSERT => 73, :HOME => 74,
    :PAGEUP => 75, :DELETE => 76, :END => 77, :PAGEDOWN => 78,
    :LCTRL => 224, :LSHIFT => 225, :LALT => 226, :RCTRL => 228, :RSHIFT => 229, :RALT => 230
  }
  ("A".."Z").each_with_index { |letra, i| ESCANCODES_WEB[letra.to_sym] = 4 + i }
  (1..9).each { |n| ESCANCODES_WEB[:"NUMBER_#{n}"] = 29 + n }
  ESCANCODES_WEB[:NUMBER_0] = 39
  (1..12).each { |n| ESCANCODES_WEB[:"F#{n}"] = 57 + n }
  LETRAS_WEB = ("A".."Z").to_a.freeze
  DIGITOS_WEB = ("0".."9").to_a.freeze
  # Teclas de letra de cada botón. empaquetar.py las deja libres para poder escribirlas:
  # el mando solo usa Enter y Escape. Fuera de un campo de texto actúan como en el nativo.
  TECLAS_WEB = { C => [:C, :SPACE], B => [:X], A => [:Z], X => [:A], Y => [:S], Z => [:D],
                 L => [:Q], R => [:W] }.freeze

  class << self
    [:pressex?, :triggerex?, :repeatex?, :releaseex?].each do |nombre|
      next unless method_defined?(nombre)
      original = instance_method(nombre)
      define_method(nombre) do |tecla|
        original.bind(self).call(tecla.is_a?(Symbol) ? (ESCANCODES_WEB[tecla] || 0) : tecla)
      end
    end

    [[:press?, :pressex?], [:trigger?, :triggerex?], [:repeat?, :repeatex?], [:release?, :releaseex?]].each do |boton, tecla|
      next unless method_defined?(boton)
      original = instance_method(boton)
      define_method(boton) do |entrada|
        return true if original.bind(self).call(entrada)
        teclas = TECLAS_WEB[entrada]
        return !teclas.nil? && !text_input && teclas.any? { |t| send(tecla, t) }
      end
    end

    def gets
      texto = +""
      mayuscula = pressex?(:LSHIFT) || pressex?(:RSHIFT)
      LETRAS_WEB.each do |letra|
        texto << (mayuscula ? letra : letra.downcase) if triggerex?(letra.to_sym)
      end
      DIGITOS_WEB.each { |digito| texto << digito if triggerex?(:"NUMBER_#{digito}") }
      texto << " " if triggerex?(:SPACE)
      return texto
    end
  end
end

unless defined?(HTTPLite)
  module HTTPLite
    SIN_RED = { status: 0, body: "" }.freeze

    def self.get(*)
      SIN_RED.dup
    end

    def self.post(*)
      SIN_RED.dup
    end

    def self.post_body(*)
      SIN_RED.dup
    end

    # PIF también usa este parser para datos locales (atuendos, textos, Pokédex).
    module JSON
      ESCAPES = { "n" => "\n", "t" => "\t", "r" => "\r", "b" => "\b", "f" => "\f",
                  '"' => '"', "\\" => "\\", "/" => "/" }.freeze

      def self.parse(texto)
        @t = texto
        @i = 0
        valor = leer_valor
        saltar_espacios
        return valor
      end

      def self.saltar_espacios
        @i += 1 while @i < @t.bytesize && " \n\r\t".include?(@t.byteslice(@i, 1))
      end

      def self.leer_valor
        saltar_espacios
        case @t.byteslice(@i, 1)
        when "{" then leer_objeto
        when "[" then leer_lista
        when '"' then leer_texto
        when "t" then @i += 4; true
        when "f" then @i += 5; false
        when "n" then @i += 4; nil
        else leer_numero
        end
      end

      def self.leer_objeto
        @i += 1
        obj = {}
        loop do
          saltar_espacios
          if @t.byteslice(@i, 1) == "}"
            @i += 1
            return obj
          end
          @i += 1 if @t.byteslice(@i, 1) == ","
          saltar_espacios
          clave = leer_texto
          saltar_espacios
          @i += 1 # ':'
          obj[clave] = leer_valor
        end
      end

      def self.leer_lista
        @i += 1
        lista = []
        loop do
          saltar_espacios
          if @t.byteslice(@i, 1) == "]"
            @i += 1
            return lista
          end
          @i += 1 if @t.byteslice(@i, 1) == ","
          lista.push(leer_valor)
        end
      end

      def self.leer_texto
        @i += 1
        salida = +""
        loop do
          # Avanza de golpe hasta la próxima comilla o barra
          fin = @i
          fin += 1 while fin < @t.bytesize && @t.getbyte(fin) != 34 && @t.getbyte(fin) != 92
          salida << @t.byteslice(@i, fin - @i)
          @i = fin
          if @t.getbyte(@i) == 34
            @i += 1
            return salida.force_encoding("UTF-8")
          end
          sig = @t.byteslice(@i + 1, 1)
          if sig == "u"
            salida << [@t.byteslice(@i + 2, 4).to_i(16)].pack("U")
            @i += 6
          else
            salida << (ESCAPES[sig] || sig.to_s)
            @i += 2
          end
        end
      end

      def self.leer_numero
        ini = @i
        @i += 1 while @i < @t.bytesize && "+-0123456789.eE".include?(@t.byteslice(@i, 1))
        crudo = @t.byteslice(ini, @i - ini)
        return (crudo =~ /[.eE]/) ? crudo.to_f : crudo.to_i
      end

      def self.stringify(obj)
        case obj
        when Hash then "{" + obj.map { |k, v| "#{k.to_s.inspect}:#{stringify(v)}" }.join(",") + "}"
        when Array then "[" + obj.map { |v| stringify(v) }.join(",") + "]"
        when String, Symbol then obj.to_s.inspect
        when nil then "null"
        else obj.to_s
        end
      end
    end
  end
end
