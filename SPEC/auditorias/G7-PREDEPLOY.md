# Gate G7 — pre-deploy del reconciliador

```
BASE       b04b0ff, ampliado con la quinta capacidad el 21/09/2026
VEREDICTO  LISTO PARA ACTIVACIÓN con las CINCO capacidades declaradas.
           NO verde en producción.
FECHA      20/09/2026 · lee_caso agregada el 21/09/2026 (B6)
ALCANCE    catálogo y verificación. Nada aplicado, nada encendido.
```

## Qué pedía G7

> T20 habilitado; **cadencia efectiva medida** y compatible con los plazos de
> Q4 (1–5 min, no el ciclo horario); una sincronización artificial de
> laboratorio recorre `pendiente → en_curso → hecha` **sin tocar un sistema
> externo real**.

Y, del cierre de B4: declarar `busca_caso` en el catálogo del tenant.

## El catálogo (`117e315`)

```
busca_caso      consultar_casos_bottlecrm      adopta el caso ya creado
asigna_caso     asignar_caso_crm               POST /cases/<id>/assignees/
lee_asignados   consultar_asignados_caso_crm   GET  /cases/<id>/assignees/
lee_perfiles    consultar_perfiles_crm         GET  /users/get-teams-and-users/
```

**Son CINCO desde B6, las cinco declaradas:**

```
busca_caso      consultar_casos_bottlecrm      adopta el caso ya creado
asigna_caso     asignar_caso_crm               POST /cases/<id>/assignees/
lee_asignados   consultar_asignados_caso_crm   GET  /cases/<id>/assignees/
lee_perfiles    consultar_perfiles_crm         GET  /users/get-teams-and-users/
lee_caso        consultar_caso_crm             GET  /api/cases/<id>/
```

**`lee_caso` apunta al GET del detalle y a nada más.** `cerrar_caso` exige las
dos —leer y cerrar—: medido contra el CRM real, un PATCH sobre un caso ya
cerrado responde 200 y le reescribe `closed_on` con la fecha del reintento. Con
la de escribir sola se podría escribir sin mirar antes, que es exactamente el
daño. Sin ambas, el efecto queda `fallida_definitiva` con su código, visible y
sin reintentos — nunca `desconocida`.

**Ninguna herramienta usa PUT ni DELETE sobre un caso**, y hay una aserción que
recorre el catálogo entero para comprobarlo: el PUT del detalle responde 200 y
vacía `contacts`, `teams` y `tags`. Cerrar con él borraría datos que nadie pidió
borrar, sin un solo error. Por eso `cierra_caso` es PATCH y `lee_caso` es GET.
Una mutación fija cada cosa.

Ver SPEC/auditorias/B6-CIERRE-DESENLACE.md.

**`asigna_caso` apunta al endpoint aditivo y a ningún otro.** `bulk/update` usa
`.set()` y el PUT del detalle hace `clear()`+`add()`: los dos reemplazan el
conjunto y borrarían a los colaboradores que un supervisor haya sumado; el PUT
además vacía contacts, teams y tags. Dos mutaciones lo fijan.

Las tres de D28 las ejecuta el **reconciliador**, no el modelo: están en el
catálogo para que T20 sepa con qué hacerlo.

## Lo que hacía falta corregir antes, y no estaba en el brief

G7 pedía declarar `busca_caso`, y eso era **imposible**. `Herramienta` usa
`extra="forbid"`, así que un YAML con esa bandera hacía fallar la carga entera —
y el código de B4 la leía con `getattr(..., False)`, que devuelve False en
silencio. La capacidad se consultaba, no se podía declarar, y nadie se
enteraba. Corregido en `86879aa`.

Si G7 se hubiera intentado antes, el YAML habría fallado la carga y el síntoma
no habría apuntado a la causa.

## La verificación

`tests/test_g7_catalogo_reconciliador.py`, **sin red, sin base y sin ejecutar
ningún efecto**. Arma el ejecutor **real** con esta config y comprueba que
reconoce los tipos:

```
crear_caso     tiene ejecutor, valida antes de llamar
asignar_caso   tiene ejecutor, valida antes de llamar
cerrar_caso    tiene ejecutor, valida antes de llamar (B6)
               y sin 'lee_caso' no se intenta: 'sin_ejecutor', nunca incierto
crear_ticket   SIGUE sin ejecutor, por el gate Q2 -- y es lo correcto
cerrar_ticket  SIGUE sin ejecutor, por lo medido en B6 -- y es lo correcto
```

Hay una aserción que cuenta las llamadas a sistemas externos y **exige cero**.
Es la traducción literal de «sin tocar un sistema externo real».

Y el **dry-run** se mide, no se lee: se espía el punto por el que pasa cualquier
llamada externa (`_ejecutor_de`) y el barrido de acciones, y una pasada seca no
toca ninguno — sólo cuenta lo elegible. Con **control positivo**: sin
`--dry-run` el mismo camino sí los arma. Sin esa segunda mitad, la primera
pasaría igual con `una_vuelta` rota.

## El worker

```
apagado por defecto              sin la variable, no procesa nada
sólo el '1' exacto lo enciende   '0', '', 'true', 'si', 'yes', '01', '2', '-1' no
cadencia 300 s                   y sale de un solo lugar, no de dos números
interruptor propio               no mira RELOJ_HABILITADO
apagado, '--once' no hace nada   comprobado, no supuesto
```

**Mutaciones: 12 probadas, 12 rojas.** Entre ellas: `asigna_caso` apunta a
`bulk/update`; usa el PUT del detalle; se quita `busca_caso`; se quita
`lee_perfiles`; el worker arranca encendido; la cadencia se va al ciclo horario.
Y las cinco de B6: se quita `lee_caso`; apunta a la **lista** de casos en vez de
al detalle; apunta a un sub-recurso que no trae `status`; cerrar el caso pasa a
**PUT**; el dry-run arma el ejecutor igual.

Un test propio se contradecía —afirmaba que `'1 '` no enciende y dos líneas
después que tolera espacios—. `encendido()` hace `strip()`, y esa es la
conducta correcta: un espacio al copiar una variable de entorno es un descuido,
no la intención de dejarlo apagado. Se corrigió la aserción, no el código.

## G7: LISTO PARA ACTIVACIÓN — no verde en producción

Lo que **no** se hizo, y hace falta para que sea verde:

```
1. aplicar la config a producción            (escribe asistente.tenant_config)
2. desplegar el servicio del worker
3. RECONCILIADOR_HABILITADO=1
4. la sincronización de laboratorio, contra el despliegue real
5. cli/diferencias_config.py rapilink        después de aplicar
```

### Dos cosas que conviene decidir antes del punto 1

**Aplicar la config toca la medición ON vs OFF.** Escribir `tenant_config` es lo
que Q3 señala como contaminante. Las **cinco** herramientas nuevas no cambian el
razonamiento del modelo —ninguna es invocable por él en la práctica; las tres de
D28 y la de B6 las llama T20— pero la escritura ocurre igual. Es decisión de
quien lleva la medición, no del despliegue.

Hasta que se aplique, `cli/diferencias_config.py rapilink` va a terminar en 1 y
señalar las cinco como «el repo lo declara y la base no». **Es la señal
correcta, no un fallo**: eso es exactamente lo que ese comando existe para
decir, y el día que se aplique tiene que dejar de decirlo.

**El endpoint aditivo tiene que estar desplegado primero.** `asigna_caso` apunta
a `/api/cases/<id>/assignees/`, que existe en este worktree y **no** en el CRM
de producción. Si la config se aplica antes que el CRM, cada `asignar_caso`
termina en `fallida_definitiva` con un 404 — visible y sin daño, pero ruido
evitable. El orden correcto es: CRM primero, config después, worker al final.

**Y antes del despliegue final: G6**, sobre `messages` poblada.
