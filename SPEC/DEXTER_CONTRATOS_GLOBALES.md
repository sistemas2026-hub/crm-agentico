# DEXTER — CONTRATOS GLOBALES

Congelados. Aplican a toda sesión sin repetirlos en el prompt. Un prompt dice
"aplican íntegramente SPEC/DEXTER_CONTRATOS_GLOBALES.md" y eso basta.

Cambiar algo de acá requiere decisión explícita registrada, no una sesión que
lo reinterprete.

---

## ENTREGA

```
aceptado ≠ entregado ≠ leído          tres hechos distintos
el relevo usa SOLO el primero
whatsapp: Meta devolvió wamid  →  estado_entrega = 'enviado'
```

```
unknown ≠ failed
```
`incierto`, `sin_id` y `aceptado_sin_registro` NO son rechazo. Sólo `rechazado`
(4xx definitivo) habilita avisar al operador y ofrecer reintento. Un `pendiente`
o `desconocido` jamás se reenvía: el cliente lo recibiría dos veces.

La distinción ya es durable: `devolucion_fallida` persiste `datos.resultado`.
La UI lee ese campo, nunca el nombre del evento.

## RELEVO

```
T6 = responder y devolver     T7 = devolver sin responder
T7 ≠ recovery de T6           T7 ≠ prueba de aceptación
```
Invariante: **ningún camino pone `control = ia` por T6 sin que estén durablemente
persistidos `wamid` + `estado_entrega = 'enviado'`.** Verificado en el draft (D1c).

```
G9 verde NO activa T6 automáticamente
control se decide con control_efectivo(), nunca con las banderas sueltas
dueño durable de Dexter (asignada_a) ≠ dueño del ticket del CRM (D28)
legado sin relevo → legado_sin_relevo, nunca reasignación silenciosa
```

## PERSISTENCIA

```
guardar primero, entregar después     un fallo de entrega nunca borra lo escrito
ninguna transacción abierta durante una llamada de red
transacciones cortas, FOR UPDATE, idempotencia por clave, fail-closed
un éxito que no quedó registrado no es un éxito
```

Idempotencia real = clave **estable** derivada de algo durable.
Un uuid nuevo por intento es un identificador único, **no** una clave idempotente.
Ninguna clave puede contener `None`: colisiona entre clientes del mismo tenant.

## ARQUITECTURA

```
nucleo/ = motor genérico, nunca conoce un cliente
tenants/ = configuración por empresa, sin código
```
Todo dato que varía por empresa es configuración editable y persistida por tenant.
"Hoy sólo hay un tenant" no justifica hardcodear.

## PRIVACIDAD Y LOGS

```
nunca leer .env
payload raw de Meta: sólo al log, nunca persistido ni mostrado (D19/D20/D23)
autor_nombre NO va a logs, traces, excepciones ni telemetry
los logs llevan metadata: id_interno(), ref_proveedor(), ref_sesion()
```

## OPERACIÓN

```
push a fix/integracion-wisphub = DEPLOY A PRODUCCIÓN
un solo dueño de producción; las demás sesiones entregan hashes
no conectar a producción para obtener capturas
no crear mocks productivos
no amend
horas siempre en America/Bogota al reportar (la base es UTC)
nunca `pnpm check` en Windows con Docker arriba (usar docker exec, o worktree
  aislado sin contenedor de frontend)
```

## MÉTODO

```
afirmar sobre el EFECTO, nunca sobre la presencia del mecanismo
una prueba que dice que algo EXISTE no prueba que funcione
verificar antes de afirmar; distinguir VERIFICADO de INFERIDO
nunca declarar que un test pasó si no se ejecutó
PARSEA ≠ IMPORTA ≠ FUNCIONA
"no detectadas por chequeo estático" ≠ "no hay diferencias"
```
