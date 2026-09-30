# DECISIONES DE NEGOCIO APROBADAS

> Solo decisiones de **negocio** ya aprobadas. Lo técnico no aprobado no entra acá — vive en
> [HALLAZGOS_AUDITORIA.md](HALLAZGOS_AUDITORIA.md) como pendiente, o en
> [FUERA_DE_ALCANCE.md](FUERA_DE_ALCANCE.md) como límite.
>
> Origen: [MASTER_SPEC_CRM_AGENTE_IA_RAPILINK_v1.2.md](MASTER_SPEC_CRM_AGENTE_IA_RAPILINK_v1.2.md) §3 y §11.
> Donde se indica "cómo se refleja hoy", es una constatación del sistema actual, no una decisión nueva.

---

## Reclamo formal

**Cada empresa define su propio criterio.** No existe —ni debe escribirse— una definición universal rígida en código sobre qué constituye un reclamo formal: depende de la operación y de la experiencia de cada empresa.

`reclamo_formal` es uno de los casos del catálogo, y sus criterios de detección son configuración por tenant.

## Consulta de factura

**Autoservicio.** El cliente la resuelve con el agente, sin intervención humana.

## Consulta de saldo

**Autoservicio.** Igual criterio que la consulta de factura.

## Métodos de pago

**Configurables por empresa.** Cada empresa podrá cargar sus propios métodos de pago para que el agente los informe al cliente cuando se lo pidan. No se hardcodean como una lista global del motor.

## Comprobante de pago

Trabajo repartido, y el reparto es la decisión:

| El agente | La persona |
|---|---|
| Recibe el comprobante | Valida que el pago sea real |
| Preclasifica | Registra el pago en WispHub |
| Recopila la información necesaria | |
| Escala | |

El agente **no** da por válido un pago ni lo registra.

*Cómo se refleja hoy:* `reportar_comprobante_pago` es la herramienta del agente de cara al cliente (`facturacion_cliente`); recibe y escala, no registra.

## Pago

**El registro financiero lo hace una persona, en WispHub.** Está dentro del alcance actual como proceso humano.

*Cómo se refleja hoy:* la herramienta `registrar_pago` existe y funciona, pero está disponible **solo para el rol interno `facturacion`** (un colaborador), nunca para el agente que atiende al cliente.

## Reconexión

**Proceso humano en WispHub.** Misma lógica que el pago: la decisión y la ejecución son de una persona.

## WiFi

| El agente | La persona |
|---|---|
| Recopila los datos del cambio | Ejecuta el cambio sobre el equipo |
| Valida que sean correctos | |
| Resume | |
| Escala | |

El agente nunca toca el equipo del cliente.

## Conversación

- **Se considera resuelta cuando el requerimiento está resuelto** — no cuando se deja de escribir.
- **La inactividad, por sí sola, no significa que el problema esté resuelto.** Un cierre por inactividad no puede registrarse como una resolución.

## Áreas visitadas

- Se mantiene la protección **anti-rebote**: una conversación no debe volver a rebotar entre áreas.
- Debe **persistirse el estado mínimo necesario** para sobrevivir a un reinicio.
- **Decisión aprobada; la implementación sigue pendiente** (ver [HALLAZGOS_AUDITORIA.md](HALLAZGOS_AUDITORIA.md) → Pendientes).

## Estados de conversación

El modelo persistente es **ortogonal**: `estado`, `escalada_a_humano`, `atendida_manual`, `atendida_por`, `estado_escalada`. La vista conceptual de estados (NORMAL / ESCALADA / ESCALADA_SIN_ATENDER / ESCALADA_ATENDIDA / CERRADA) **no sustituye** ese modelo.

`NO_DETERMINADO` es un **estado válido** de escalamiento: significa que no se pudo decidir si correspondía escalar. No es lo mismo que "se escaló", y convertirlo en escalada escondería el problema.
