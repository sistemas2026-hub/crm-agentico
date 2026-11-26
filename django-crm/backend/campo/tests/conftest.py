"""Lo comun a las pruebas de campo."""
import pytest


@pytest.fixture(autouse=True)
def sin_ip_automatica(monkeypatch):
    """`firmar` asigna la IP preguntandole al motor (26/11/2026). En las
    pruebas no hay motor: por defecto no hay ninguna libre. Las que prueban la
    asignacion ponen la suya."""
    from campo import contrato

    monkeypatch.setattr(contrato, "_ip_automatica", lambda org, id_zona: "")
