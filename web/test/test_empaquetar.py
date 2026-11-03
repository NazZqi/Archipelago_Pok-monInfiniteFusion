import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from empaquetar import STRING_VACIO, descifrar_dat, quitar_vacios


def test_cada_string_vacio_de_una_racha_pasa_a_un_nil():
    cabecera = b"\x04\x08[\x02\x90\x01"
    # Un nil de menos desalinea todo lo que sigue en el stream de Marshal
    assert quitar_vacios(cabecera + STRING_VACIO * 400 + b"T") == cabecera + b"0" * 400 + b"T"


def test_un_vacio_suelto_no_se_toca():
    # Puede estar dentro de un blob de OrderedHash, que declara su largo
    suelto = STRING_VACIO + b"x" + STRING_VACIO * 400
    assert quitar_vacios(suelto) == STRING_VACIO + b"x" + b"0" * 400


def test_descifrar_deja_igual_lo_que_no_es_marshal():
    assert descifrar_dat(b"sin cifrar") == b"sin cifrar"
