from app.core.seguridad import escribir_token, generar_token, token_valido


def test_token_tiene_al_menos_256_bits_y_es_unico():
    primero = generar_token()
    segundo = generar_token()

    assert len(primero) >= 43
    assert primero != segundo


def test_escribe_token_sin_dejar_temporales(tmp_path):
    ruta = tmp_path / "runtime" / "sesion.token"

    escribir_token(ruta, "secreto")

    assert ruta.read_text(encoding="utf-8") == "secreto"
    assert not (tmp_path / "runtime" / "sesion.token.tmp").exists()


def test_valida_token_con_comparacion_segura():
    assert token_valido("abc", "abc")
    assert not token_valido("abd", "abc")
    assert not token_valido(None, "abc")
    assert not token_valido("", "abc")
