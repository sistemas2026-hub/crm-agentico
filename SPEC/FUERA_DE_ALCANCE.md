# FUERA DE ALCANCE

> Lo que el agente de desarrollo **NO** debe implementar sin una autorización nueva y explícita.
>
> Cada punto dice **qué sí existe hoy** y **dónde está el límite**, para que quede claro que no se trata de borrar lo construido: se trata de no cruzar la línea sin permiso.
>
> Origen: [MASTER_SPEC_CRM_AGENTE_IA_RAPILINK_v1.2.md](MASTER_SPEC_CRM_AGENTE_IA_RAPILINK_v1.2.md) §19.

---

## 1. Automatización del registro de pagos

**Qué sí existe:** la herramienta `registrar_pago`, funcionando y verificada contra un pago real. Está disponible **solo para el rol interno `facturacion`** — un colaborador.

**El límite:** el agente que atiende al cliente no registra pagos. La decisión de negocio es que el registro financiero lo hace una persona en WispHub. No conectar `registrar_pago` a un rol de cara al cliente, ni encadenarlo automáticamente después de recibir un comprobante.

## 2. Automatización de reconexiones

**Qué sí existe:** la API de WispHub permite reactivar el servicio al registrar un pago (es un parámetro de esa misma llamada).

**El límite:** reconectar es un proceso humano. No construir un flujo donde el agente decida y ejecute la reconexión por su cuenta.

## 3. Cambios directos de WiFi sobre equipos de clientes

**Qué sí existe:** el agente recopila los datos del cambio, los valida, los resume y escala — con protección para que un pedido incompleto no escale como si estuviera listo.

**El límite:** la ejecución del cambio sobre el equipo la hace una persona. No agregar herramientas que escriban configuración WiFi en el equipo del cliente.

## 4. Reconstrucción de la lógica interna de Ventas

**Qué sí existe:** el rol `ventas`, con catálogo curado de planes por localidad, chequeo de cobertura y el enlace al formulario real de contratación. La captura de documentos y firma sigue siendo el formulario externo de siempre.

**El límite:** Ventas es **integración**, no reimplementación. No duplicar ni rediseñar esa lógica: fue construida aparte y se integra tal como está.

## 5. Creación automática real del cliente en WispHub

**Qué sí existe:** el endpoint de alta de cliente de WispHub está documentado y fue verificado end-to-end en su momento, así que se sabe que técnicamente se puede.

**El límite:** **ninguna herramienta del catálogo lo expone**, y así debe seguir. Dar de alta un cliente real es una decisión comercial y contable, no una acción de un agente conversacional.

## 6. Reglas universales de negocio que deben ser configurables por tenant

**Qué sí existe:** el mecanismo completo para que un dato varíe por empresa sin tocar código — configuración validada y versionada en base, editable desde la interfaz, con variables de tenant para lo que no es secreto y referencias por nombre para lo que sí.

**El límite:** si al escribir código en el núcleo aparece la necesidad de distinguir una empresa, **no se resuelve con un `if`**: significa que falta un campo en la configuración. Criterios como el de `reclamo_formal` o los métodos de pago son por tenant, no globales. Hay una guarda automatizada que falla si el núcleo menciona a un cliente.

## 7. Modificaciones arquitectónicas mayores no contempladas

**Qué sí existe:** la separación núcleo/tenant, el motor como servicio único, la persistencia con aislamiento por fila que falla cerrado, y el patrón de dos capas de seguridad (el prompt guía, el código garantiza).

**El límite:** no cambiar esos cimientos —mover garantías del código al prompt, romper la separación núcleo/tenant, reemplazar el modelo de persistencia o el de sesiones— sin una decisión explícita. Migrar a un servidor WSGI con varios workers entra en esta categoría: es correcto hacerlo algún día, pero primero hay que resolver el lock por conversación, porque hoy la seguridad frente a concurrencia es accidental.

## 8. Cambios de integración externa no aprobados

**Qué sí existe:** WispHub, SmartOLT, WhatsApp, DeepSeek (modelo) y OpenAI (embeddings), cada uno con su contrato verificado en vivo.

**El límite:** no conectar sistemas externos nuevos, ni cambiar de proveedor de modelo, ni ampliar lo que se le manda a uno existente, sin autorización. Para conectar algo nuevo ya existe el camino previsto: sondeo real de la API y aprobación humana antes de que llegue al catálogo.

---

## Regla general

Ante una decisión que falte:

> **NO IMPLEMENTAR → DOCUMENTAR → PROPONER → ESPERAR APROBACIÓN**
