# MASTER SPEC — CRM + AGENTE IA MULTITENANT — RAPILINK

**Versión:** 1.2
**Estado:** Aprobado como fuente de verdad para implementación

## 1. Objetivo y alcance
Definir el comportamiento integral del CRM + agentes IA, con arquitectura multitenant, trazabilidad, seguridad y separación clara entre automatización y trabajo humano.

### Gobierno documental

Esta MASTER SPEC es la **fuente de verdad para la implementación del sistema completo**, no solo del flujo de atención. Su gobierno incluye explícitamente:

- `configuracion_guiada`;
- habilidades;
- consumo del LLM;
- tarifas;
- tope de gasto;
- saldo del proveedor;
- la funcionalidad asociada de consumo.

Estos componentes **ya existen en el sistema**: se incorporan aquí formalmente, sin crear reglas de funcionamiento nuevas.

`PRD.md` y `ARQUITECTURA.md` son **documentación complementaria / histórica**. Aportan contexto, motivos y detalle de implementación, pero **no son fuente de verdad para la implementación cuando difieran de esta SPEC**. No se modifican como parte de este documento.

## 2. Principios no negociables
- La IA no inventa datos, resultados, acciones ni estados.
- Las decisiones críticas se protegen en código.
- Los datos operativos se consultan desde la fuente correspondiente.
- Lo configurable por empresa no se hardcodea como regla global.
- Lo que no esté decidido no debe ser inventado por Claude.

## 3. Decisiones de negocio aprobadas
- `reclamo_formal`: configurable por empresa según necesidad y experiencia.
- `consulta_factura`: autoservicio.
- Métodos de pago: configurables por empresa para consultas futuras.
- Comprobante de pago: agente recibe/preclasifica y escala; humano valida y registra.
- Pago y reconexión: proceso humano en WispHub dentro del alcance actual.
- WiFi: agente recopila/valida; humano ejecuta el cambio.
- Conversación normal: se cierra cuando el requerimiento está resuelto.
- Inactividad no equivale automáticamente a resolución.
- `areas_visitadas`: anti-rebote persistente, con el estado mínimo necesario tras reinicio.
- Estados de conversación: el modelo persistente es ortogonal (`estado`, `escalada_a_humano`, `atendida_manual`, `atendida_por`, `estado_escalada`); la vista conceptual no debe sustituir ese modelo. `NO_DETERMINADO` es un estado válido de escalamiento.

## 4. Arquitectura
WhatsApp / CRM → Motor IA → Router → Agente especializado → Herramientas/datos → Respuesta o escalamiento.

Fuentes de verdad: WispHub para datos de servicio/facturación; SmartOLT para diagnóstico técnico; CRM para casos; base del asistente para continuidad; `tenant_config` para configuración por empresa.

## 5. Agentes y routing
- `cliente_final`: entrada y routing.
- `facturacion_cliente`: consultas de cartera/facturas.
- `soporte_tecnico_cliente`: diagnóstico y acciones autorizadas.
- `ventas`: integración con solución existente.
- Agentes internos: facturacion/cartera, soporte, administración y otros roles configurados.
- Rol adicional confirmado: `configuracion_guiada`. El sistema actual tiene 8 roles configurados por tenant; la lista exacta proviene de la configuración vigente.

`derivar_a_area` es la herramienta de routing. `areas_visitadas` evita rebotes.

## 6. Casos
`no_internet`, `internet_lento`, `sin_senal_tv`, `cambio_wifi`, `consulta_saldo`, `consulta_factura`, `estado_servicio`, `reconexion`, `reclamo_formal`, `validacion_de_pago`, `otro`.

`caso_manual` es una clasificación persistida distinta de área, escalamiento, ticket y conversación.

## 7. Seguridad
Identidad cliente en pasos; identidad colaborador derivada de autenticación; defensa contra IDOR/cross-tenant; no divulgación de prompts, herramientas, secretos o datos de otros clientes; controles críticos en código.

## 8. Escalamiento
Solicitud de humano, frustración, tres fallos, visita, datos insuficientes, acción sin efecto, identidad no resuelta, fallos técnicos reales. Resumen técnico: RESUMEN / QUÉ YA SE PROBÓ / NO SE PUDO COMPROBAR / SIGUIENTE PASO / ADJUNTOS.

## 9. Integraciones
CRM ↔ WhatsApp ↔ WispHub con conversación como mediador. SmartOLT para estado/diagnóstico. Ventas solo integración.

## 10. WiFi
Recopilar + validar + resumir + escalar; ejecución humana.

## 11. Facturación y pagos
Consulta de saldo/factura autoservicio. Métodos de pago configurables. Comprobante: preclasificación y escalamiento. Registro/reconexión humanos.

## 12. Memoria y continuidad
Rol/caso/ticket/estado desde DB; identidad verificada puede requerir revalidación tras reinicio; datos técnicos dinámicos se reconsultan; persistir estado mínimo anti-rebote; decisiones de seguridad no deben depender solo de RAM.

## 13. Estados e idempotencia
Estados: NORMAL, ESCALADA, ESCALADA_SIN_ATENDER, ESCALADA_ATENDIDA, CERRADA. Idempotencia para webhook, escalamiento, tickets, acciones físicas, respuestas humanas y cierres.

## 14. Observabilidad
`tool_calls`, verificaciones, conversación, caso, ticket y correlación por `conversation_id`. Enmascarar datos sensibles.

## 15. Concurrencia y resiliencia
Lock por conversación antes de múltiples workers; no usar RAM para controles críticos; reconciliación; recuperación ante timeout.

## 16. Configuración por tenant
Configuración independiente por empresa. `reclamo_formal` y métodos de pago son tenant-configurable. Protección de `tenant_config` contra código adelantado, atrasado y estado indeterminado.

## 17. Pruebas
50 Golden Cases existentes + cobertura dirigida para `caso_manual`, reclamo formal, consulta factura, restart, anti-rebote, errores técnicos, concurrencia, idempotencia y seguridad.

## 18. Pendientes técnicos
- Persistencia de `areas_visitadas` (decisión aprobada en §3; implementación pendiente).
- **Identidad autenticada del colaborador.** `atendida_por` **ya existe como atributo persistente y se utiliza actualmente**: el pendiente **no** es crear la columna. Lo pendiente es fortalecer la identidad autenticada del colaborador, su vínculo con `profile_id`, la trazabilidad de quién ejecutó cada acción o mensaje, y la consistencia entre la identidad autenticada y el atributo persistido. No se propone una columna nueva salvo que resulte estrictamente necesario.
- Idempotencia de respuestas humanas/escrituras externas.
- Reconciliación CRM↔WispHub.
- Health checks/alertas.
- Política de historial largo/resumen.

## 19. Fuera de alcance
Automatización de pago/reconexión, cambio directo de WiFi, duplicación de Ventas, creación automática real de cliente en WispHub, reglas universales que corresponden a cada tenant.

## 20. Reglas para Claude
Claude construye conforme a la SPEC. Si falta una decisión: **NO IMPLEMENTAR → DOCUMENTAR → PROPONER → ESPERAR APROBACIÓN**.

Ciclo: SPEC → plan → implementación → pruebas → evidencia → revisión → aprobación → deploy.
