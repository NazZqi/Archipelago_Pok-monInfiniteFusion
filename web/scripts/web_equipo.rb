# Combates amistosos e intercambios de la versión web. juego.js deja una orden en
# red_ordenes.txt; aquí se borra y cada orden deja una respuesta en red_respuesta.txt. La página
# nunca borra estos archivos: si borra uno que wasmfs ya abrió, lo que Ruby escribe se pierde.
# El servidor guarda equipos y ofertas.
# Un Pokémon viaja como una línea de texto, nunca como Marshal: aquí se valida contra GameData
# y server.mjs (limpiarPokemon) revisa la forma.
#   especie|nivel|movs|habilidad|naturaleza|objeto|ivs|evs|shiny|género|apodo|personalID
module WebEquipo
  STATS = [:HP, :ATTACK, :DEFENSE, :SPECIAL_ATTACK, :SPECIAL_DEFENSE, :SPEED]
  TIPOS = { "m" => :POKEMONTRAINER_Red, "f" => :POKEMONTRAINER_Leaf }

  class << self
    def linea(pk)
      apodo = pk.name.to_s.gsub(/[|\t\r\n]/, " ")[0, 20]
      [pk.species, pk.level, pk.moves.map(&:id).join(","), pk.ability_index.to_i.clamp(0, 2),
       pk.nature_id, pk.item_id, STATS.map { |s| pk.iv[s].to_i.clamp(0, 31) }.join(","),
       STATS.map { |s| pk.ev[s].to_i.clamp(0, 252) }.join(","), pk.shiny? ? 1 : 0, pk.gender.to_i,
       apodo, pk.personalID.to_i].join("|")
    end

    # nil si algo no existe en este juego: el Pokémon se descarta
    def pokemon(texto, dueno = $Trainer)
      c = texto.to_s.split("|", -1)
      return nil if c.length != 12
      especie = c[0].to_sym
      return nil unless GameData::Species.try_get(especie)
      nivel = c[1].to_i
      return nil unless nivel.between?(1, GameData::GrowthRate.max_level)
      pk = Pokemon.new(especie, nivel, dueno, false)
      pk.personalID = c[11].to_i
      c[2].split(",").each { |m| pk.learn_move(m.to_sym) if GameData::Move.exists?(m.to_sym) }
      pk.reset_moves if pk.moves.empty?
      pk.ability_index = c[3].to_i.clamp(0, 2)
      pk.nature = c[4].to_sym if GameData::Nature.exists?(c[4].to_sym)
      pk.item = c[5].to_sym if !c[5].empty? && GameData::Item.exists?(c[5].to_sym)
      ivs = c[6].split(",").map(&:to_i)
      evs = c[7].split(",").map(&:to_i)
      STATS.each_with_index do |s, i|
        pk.iv[s] = ivs[i].to_i.clamp(0, 31)
        pk.ev[s] = evs[i].to_i.clamp(0, 252)
      end
      pk.shiny = (c[8] == "1")
      pk.gender = c[9].to_i
      pk.name = c[10] if !c[10].empty? && c[10] != pk.speciesName
      pk.calc_stats
      pk.heal
      return pk
    rescue StandardError => e
      STDERR.puts("[web-equipo] #{e.class}: #{e.message}")
      return nil
    end

    def exportar
      return unless $Trainer
      File.write(ruta("red_equipo.txt"), $Trainer.party.reject(&:egg?).map { |pk| linea(pk) }.join("\n"))
    end

    # Solo en el mapa, sin diálogo, sin evento corriendo y quieto: como la cola de ArchipelagoNetwork
    def atender
      archivo = ruta("red_ordenes.txt")
      return unless File.exist?(archivo) && libre?
      campos = File.read(archivo).chomp.split("\t", -1)
      File.delete(archivo)
      respuesta = case campos[0]
                  when "combate" then combatir(*campos[1..])
                  when "ofrecer" then ofrecer(*campos[1, 2])
                  when "aceptar" then aceptar(*campos[1, 3])
                  when "recibir" then recibir(*campos[1, 3])
                  end
      # juego.js no manda otra orden hasta ver esta respuesta
      File.write(ruta("red_respuesta.txt"), respuesta || "hecho")
    rescue StandardError => e
      STDERR.puts("[web-equipo] #{e.class}: #{e.message}")
      File.write(ruta("red_respuesta.txt"), "error\t#{e.message}") rescue nil
    end

    private

    def ruta(nombre)
      File.join(System.data_directory, nombre)
    end

    def libre?
      $scene.is_a?(Scene_Map) && $game_temp && !$game_temp.message_window_showing &&
        !$game_temp.in_battle && $game_player && !$game_player.moving? && !pbMapInterpreterRunning?
    end

    def combatir(nombre, genero, *lineas)
      equipo = lineas.map { |l| pokemon(l, nil) }.compact
      if equipo.empty?
        pbMessage(_INTL("El equipo de {1} no se pudo cargar.", nombre))
        return nil
      end
      tipo = TIPOS[genero] || TIPOS["m"]
      $PokemonTemp.battleRules["expGain"] = false
      $PokemonTemp.battleRules["moneyGain"] = false
      customTrainerBattle(nombre, tipo, equipo, 50, _INTL("¡Buen combate!"), nil, nil, [], true)
      $Trainer.heal_party
      return nil
    end

    def elegir(texto)
      pbMessage(texto)
      elegido = nil
      pbFadeOutIn {
        escena = PokemonParty_Scene.new
        pantalla = PokemonPartyScreen.new(escena, $Trainer.party)
        pantalla.pbStartScene(_INTL("Elige un Pokémon."), false)
        i = pantalla.pbChoosePokemon
        pantalla.pbEndScene
        elegido = $Trainer.party[i] if i && i >= 0
      }
      return elegido && !elegido.egg? ? elegido : nil
    end

    def ofrecer(para, nombre)
      pk = elegir(_INTL("¿Qué Pokémon le ofreces a {1}?", nombre))
      return "cancelado" unless pk
      return "oferta\t#{para}\t#{linea(pk)}"
    end

    def aceptar(id, nombre, texto)
      suyo = pokemon(texto, nil)
      unless suyo
        pbMessage(_INTL("El Pokémon que ofrece {1} no existe en este juego.", nombre))
        return "cancelado"
      end
      return "cancelado" unless pbConfirmMessage(_INTL("{1} te ofrece a {2} (Nv. {3}). ¿Aceptas?",
                                                       nombre, suyo.name, suyo.level))
      pk = elegir(_INTL("¿Qué Pokémon le das a cambio?"))
      return "cancelado" unless pk
      return "aceptacion\t#{id}\t#{linea(pk)}"
    end

    # Cambia el Pokémon propio por el recibido una sola vez: si el que sale ya no está, el cambio
    # se aplicó antes de una recarga y no se repite
    def recibir(id, pid_sale, texto)
      sale = buscar(pid_sale.to_i)
      llega = pokemon(texto)
      if sale && llega
        llega.obtain_method = 2 if llega.respond_to?(:obtain_method=)  # obtenido por intercambio
        quitar(sale)
        pbAddPokemonSilent(llega)
        Game.save
        pbMessage(_INTL("¡Recibiste a {1}!", llega.name))
      elsif !sale && !buscar(llega&.personalID)
        pbMessage(_INTL("El intercambio no se aplicó: tu Pokémon ya no está en el equipo ni en el PC."))
      end
      return "recibido\t#{id}"
    end

    def buscar(pid)
      return nil unless pid
      encontrado = $Trainer.party.find { |pk| pk.personalID == pid }
      return encontrado if encontrado
      $PokemonStorage.maxBoxes.times do |caja|
        $PokemonStorage.maxPokemon(caja).times do |i|
          pk = $PokemonStorage[caja, i]
          return pk if pk && pk.personalID == pid
        end
      end
      return nil
    end

    def quitar(pk)
      i = $Trainer.party.index(pk)
      return $Trainer.party.delete_at(i) if i
      $PokemonStorage.maxBoxes.times do |caja|
        $PokemonStorage.maxPokemon(caja).times do |j|
          return $PokemonStorage[caja, j] = nil if $PokemonStorage[caja, j].equal?(pk)
        end
      end
    end
  end
end

# El equipo que ven los amigos se actualiza cada vez que se guarda
module Game
  class << self
    alias_method :web_equipo_save, :save
    def save(*args, **kwargs)
      ok = web_equipo_save(*args, **kwargs)
      WebEquipo.exportar if ok
      return ok
    end
  end
end
