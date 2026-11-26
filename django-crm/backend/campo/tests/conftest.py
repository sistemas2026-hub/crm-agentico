"""Lo comun a las pruebas de campo."""
import pytest


@pytest.fixture(autouse=True)
def sin_ip_automatica(monkeypatch):
    """`firmar` asigna la IP preguntandole al motor (26/11/2026). En las
    pruebas no hay motor: por defecto no hay ninguna libre. Las que prueban la
    asignacion ponen la suya."""
    from campo import contrato

    monkeypatch.setattr(contrato, "_ip_automatica", lambda org, id_zona: "")


@pytest.fixture(autouse=True)
def sin_preguntar_ip_en_vivo(monkeypatch):
    """Y antes de poner una IP se le pregunta al proveedor si sigue libre
    (26/11/2026). En las pruebas NUNCA sale esa pregunta: el motor del entorno
    tiene claves reales. Por defecto «no se pudo saber»; las que lo prueban
    ponen su respuesta."""
    from campo.services import ips_libres

    monkeypatch.setattr(ips_libres, "libre_en_el_proveedor", lambda org, ip: None)
