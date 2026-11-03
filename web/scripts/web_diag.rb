# Solo con empaquetar.py --diagnostico: nunca en el paquete que se publica.

# Medidor para la prueba de viabilidad: FPS reales cada 200 frames, por stderr.
module Graphics
  class << self
    alias_method :__web_update, :update

    def update
      __web_update
      @web_n = (@web_n || 0) + 1
      web_ejecutar_comando if @web_n % 20 == 0
      return if @web_n % 200 != 0
      ahora = Time.now
      STDERR.puts("[web-fps] #{(200 / (ahora - @web_t)).round(1)}") if @web_t
      @web_t = ahora
    end

    # Solo para la prueba de viabilidad: ejecuta el Ruby que deje la página en
    # web_cmd.rb. También demuestra que JS y el juego pueden hablar por archivos.
    def web_ejecutar_comando
      ruta = File.join(System.data_directory, "web_cmd.rb")
      return unless File.exist?(ruta)
      codigo = File.read(ruta)
      File.delete(ruta)
      begin
        STDERR.puts("[web-cmd] #{eval(codigo, TOPLEVEL_BINDING).inspect}")
      rescue Exception => e
        STDERR.puts("[web-cmd] ERROR #{e.class}: #{e.message}")
      end
    end
  end
end
