# -*- coding: utf-8 -*-
"""
NUCLEO  -  el motor generico.

REGLA UNICA E INNEGOCIABLE DE ESTE PAQUETE:
    aqui NO puede aparecer el nombre de ningun cliente.

Ni el slug de una empresa, ni un endpoint suyo, ni una regla de negocio suya,
ni una rama condicional que lo distinga. Todo eso vive en
tenants/<slug>.config.yaml.

Si al escribir codigo aqui aparece la necesidad de distinguir un cliente, eso
significa que falta un campo en la configuracion. La salida es agregar el
campo, nunca la rama condicional.

Lo hace cumplir tests/test_nucleo_sin_tenants.py, que falla si el slug de
cualquier tenant aparece bajo este paquete.
"""
