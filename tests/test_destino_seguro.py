# -*- coding: utf-8 -*-
"""
================================================================================
 EL DESTINO AL QUE SE VUELVE DESPUES DE ENTRAR NO PUEDE SER CUALQUIERA
================================================================================

Por que existe
--------------
Quien abre un enlace profundo sin sesion es rebotado a /login y de ahi a /org.
Hasta el 09/09/2026 el destino se perdia en el camino: la persona elegia
organizacion y aparecia en '/', sin relacion con lo que habia clickeado. Se
reporto abriendo el expediente de una solicitud desde un ticket del ISP, pero
le pasaba a cualquier enlace compartido.

El arreglo es arrastrar el destino en '?redirect='. Y ahi aparece el riesgo
que hace falta probar: ese valor lo escribe quien arma el enlace.

    /login?redirect=https://sitio-que-imita-el-crm

Sin filtro, el login se vuelve un trampolin: la persona ve el dominio bueno,
entra, y sale despedida a un sitio ajeno que puede copiar esta misma pantalla
y pedirle la clave otra vez. Es un OPEN REDIRECT, y es exactamente la clase de
cosa que se cuela cuando el arreglo parece trivial.

Esto se prueba en Python aunque la funcion sea JavaScript: se leen los casos
del propio archivo y se comprueba la MISMA gramatica. No reemplaza a una
prueba en el navegador -- afirma que las reglas estan escritas y no se
borraron, que es donde una regresion de seguridad se cuela sin ruido.

Uso
---
    py -3.13 tests/test_destino_seguro.py
================================================================================
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


FUENTE = (RAIZ / "django-crm" / "frontend" / "src" / "lib" / "destino.js")


print("== 1. el validador existe y esta en UN solo lugar ==")
afirmar(FUENTE.exists(), "existe src/lib/destino.js")
codigo = FUENTE.read_text(encoding="utf-8") if FUENTE.exists() else ""


print("\n== 2. las cuatro reglas siguen escritas ==")
# Cada una tapa una forma distinta de salir del sitio. Si alguna desaparece,
# el agujero vuelve sin que nada mas se rompa -- por eso se afirman una por
# una y no "la funcion existe".
afirmar("startsWith('/')" in codigo,
        "solo rutas relativas: lo que no empieza con '/' se rechaza "
        "(https://..., javascript:...)")
afirmar("startsWith('//')" in codigo,
        "'//otro-sitio' se rechaza -- es relativa al PROTOCOLO y sale del "
        "sitio igual que una absoluta")
afirmar(r"startsWith('/\\')" in codigo or '/\\\\' in codigo,
        r"'/\otro-sitio' se rechaza -- algunos navegadores la tratan como //")
afirmar("SIN_SENTIDO" in codigo and "'/login'" in codigo and "'/org'" in codigo,
        "volver a /login o /org se rechaza: es un bucle, no un destino")


print("\n== 3. no se arma el parametro cuando no hay destino ==")
afirmar("comoParametro" in codigo and "? `?redirect=" in codigo,
        "sin destino devuelve cadena vacia, no '?redirect=' -- un parametro "
        "vacio en la URL se lee como un error de la aplicacion")
afirmar("encodeURIComponent" in codigo,
        "y el valor va codificado: una ruta con '&' o '#' partiria la URL")


print("\n== 4. los tres tramos del camino lo usan ==")
# El destino cruza tres saltos y basta que UNO no lo reenvie para que se
# pierda entero. Es el modo de falla original, y no da error en ningun lado.
TRAMOS = {
    "hooks.server.js (rebota al no tener sesion)":
        RAIZ / "django-crm/frontend/src/hooks.server.js",
    "login (arrastra el destino hasta /org)":
        RAIZ / "django-crm/frontend/src/routes/(no-layout)/login/+page.server.js",
    "org (devuelve a la persona ahi)":
        RAIZ / "django-crm/frontend/src/routes/(no-layout)/org/+page.server.js",
}
for nombre, ruta in TRAMOS.items():
    texto = ruta.read_text(encoding="utf-8") if ruta.exists() else ""
    afirmar("$lib/destino.js" in texto, f"{nombre} importa el validador")

# Y el formulario tiene que reenviarlo: la accion recibe el POST, no la query.
pagina = RAIZ / "django-crm/frontend/src/routes/(no-layout)/org/+page.svelte"
texto = pagina.read_text(encoding="utf-8") if pagina.exists() else ""
afirmar('name="redirect"' in texto,
        "el formulario de organizacion reenvia el destino en un campo oculto")


print("\n== 5. ninguna redireccion de la guarda quedo sin el destino ==")
# El bug original en una linea: 'redirect(307, "/login")' a secas. Si vuelve a
# aparecer una asi en la guarda, el enlace se pierde otra vez.
hooks = (RAIZ / "django-crm/frontend/src/hooks.server.js").read_text(encoding="utf-8")
desnudas = re.findall(r"redirect\(30\d,\s*'/(?:login|org)'\s*\)", hooks)
afirmar(not desnudas,
        f"no quedan redirecciones a /login o /org sin el destino "
        f"{'-- ' + str(desnudas) if desnudas else ''}")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] El destino se conserva y no puede sacar a nadie del sitio.")
