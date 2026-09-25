# HALLAZGOS DE AUDITORÍA — resumen consolidado

> Consolidación de las auditorías del proyecto (agosto–septiembre 2026). **No reproduce los informes completos**: los resume clasificados, para que el agente de desarrollo sepa qué está resuelto y qué no.
>
> Regla de este documento: **nada que ya esté corregido se presenta como pendiente**, y no se agregan hallazgos nuevos.

| Clase | Significa |
|---|---|
| **A. CORREGIDOS** | Había un defecto; se arregló |
| **B. IMPLEMENTADOS Y VALIDADOS** | Se construyó y se comprobó que funciona |
| **C. PENDIENTES** | Reconocido, sin implementar |
| **D. ACEPTADOS COMO DECISIÓN** | No es un defecto: se decidió así, con motivo |
| **E. LIMITACIONES CONOCIDAS** | Límite real del entorno o del alcance, documentado |

---

## A. Corregidos

- **Una acción no se daba por buena por haberse mandado el comando.** El reinicio de ONT ahora se verifica por su efecto real (`last_status_change`, un sello discreto comparado contra sí mismo), no por la respuesta del proveedor. Se descartó explícitamente "el ping mejora" como condición de éxito: el mismo equipo sano devuelve resultados distintos en corridas seguidas.
- **Un timeout del evaluador de escalamiento hacía prometer un traspaso inexistente.** Se separó en tres situaciones distintas (`ESCALAMIENTO_CONFIRMADO`, `ESCALAMIENTO_NO_CONFIRMADO`, `NO_DETERMINADO`); ninguna es la otra, y `NO_DETERMINADO` no se convierte en escalada.
- **El agendamiento quedaba colgado** al repreguntar un dato del checklist: ahora se retoma solo y la segunda vuelta termina sí o sí, en ticket o en persona.
- **Una causa de caída sin mapear dejaba al agente ciego** (la herramienta devolvía un diccionario vacío para el rol que diagnostica).
- **El asunto del ticket de una falla de fibra entraba como avería de TV** (un valor fijo pisaba el correcto).
- **`registrar_pago` estaba roto en producción** y nadie lo había notado: sin filtros verificados, la URL nunca podía resolverse. Corregido y verificado con un pago real.
- **El gate de identidad bloqueaba al rol `ventas` y a la propia derivación**, dos bugs de código que parecían de prompt.
- **`NameError` real en `cli/cargar_config.py`**: llamaba a `editor.commits_sin_empujar()` sin tener importado `editor`, así que la guarda existente nunca podía dispararse en el camino normal. Encontrado de forma independiente por dos vías (análisis estático y ejecución real) y corregido.
- **Una carga del YAML borró en silencio la tarifa y el endpoint de saldo** porque `llm` y `limites` no estaban en la lista de secciones protegidas. Corregido agregándolas, y sembrando además esos valores en el YAML.

## B. Implementados y validados

- **Solicitud explícita de persona**, en tres niveles (pedido directo, intención ambigua, confirmación), con patrones ajustados contra frases reales.
- **Escalamiento por fallos técnicos reales**, distinguiendo un error de herramienta de una condición de negocio legítima — un "no tiene facturas" no es una falla.
- **Protección de WiFi ante una condición de negocio inválida**: un pedido incompleto ya no escala como si estuviera listo.
- **Recepción y preclasificación de comprobantes de pago**, con derivación al área correcta.
- **Routing por áreas** (`derivar_a_area` + anti-rebote), verificado en vivo.
- **Detección de incidentes de red**, fail-closed: sin datos suficientes no afirma que la caída sea general. Al cliente solo se le dice que su caída es compartida y desde cuándo — la topología es panorama interno.
- **Protección de configuración Git en ambas direcciones** (copia adelantada, atrasada e indeterminada), centralizada y cubriendo las dos puertas de escritura. 28 aserciones.
- **Consumo del LLM**: conteo por tenant, tope de gasto que ya puede dispararse, tarifas con ventanas de horario pico y auditoría contra el saldo real del proveedor.
- **Validaciones productivas**: reinicio de ONT real, creación/respuesta/cierre de tickets reales, pago real, promesa de pago real, y lectura real del saldo del proveedor.

## C. Pendientes de implementación

- **Persistencia de `areas_visitadas`** — decisión de negocio aprobada; hoy el anti-rebote vive solo en memoria y no sobrevive a un reinicio.
- **Vínculo fuerte de la identidad del colaborador con la autenticación**, y **fortalecimiento de `atendida_por`**. La columna ya existe y se usa: lo pendiente es la trazabilidad de quién ejecutó cada acción o mensaje, su vínculo con `profile_id` y la consistencia entre identidad autenticada y atributo persistido. No hace falta una columna nueva.
- **Idempotencia de respuestas humanas.**
- **Idempotencia y reintentos de determinadas escrituras externas.**
- **Reconciliación CRM ↔ WispHub.**
- **Health checks y alertas.**
- **Política de historial largo / resumen.**
- **Pruebas dedicadas de reinicio y concurrencia.**

## D. Aceptados como decisión

- **Las conversaciones se guardan en claro, sin anonimizar.** Se evaluó anonimizar por patrones y se descartó: fiable con cédulas y teléfonos, imperfecta con nombres y direcciones — no garantizaba cumplimiento y sí degradaba el historial. La base legal es la autorización de tratamiento que firma el cliente.
- **DeepSeek para todos los roles, incluidos los que llevan PII**, amparado en esa misma autorización (Ley 1581, art. 26).
- **Las respuestas crudas de WispHub no se persisten**: traen contraseñas, GPS y cédula. La auditoría guarda solo metadatos.
- **El reinicio de ONT no pide aprobación humana**, por decisión explícita del cliente; en su lugar tiene precondiciones en código y verificación posterior del efecto.
- **La identidad verificada no sobrevive a un reinicio del proceso**: revalidar es la opción segura.
- **El árbol de diagnóstico no se apoya en TR-069**: se diseña con lo disponible para todos, y el dato de dispositivos entra como confirmación opcional.

## E. Limitaciones conocidas

- **Varios endpoints internos dependen del perímetro de red.** El motor no tiene dominio público salvo la ruta de WhatsApp — es deliberado (exponerlo abriría el asistente sin autenticación), pero implica que `/chat` y los endpoints internos no se pueden probar desde fuera del compose.
- **El commit exacto que corre el contenedor productivo no está expuesto** por la imagen ni por la plataforma de despliegue, y no hay acceso a Dokploy desde el entorno de desarrollo. Confirmar un despliegue exige a alguien con ese acceso.
- **Ninguna guarda de alineación Git detecta un retraso de despliegue** (el commit correcto en el remoto, todavía sin desplegar). Es un desfase distinto al que esas guardas cubren.
- **La suite completa tiene la limitación conocida de `reportlab`**: `tests/test_informes.py` falla en el entorno local por esa dependencia ausente, sin relación con el código del proyecto.
- **No existe un segundo tenant** para una prueba empírica completa de aislamiento. El aislamiento está verificado a nivel de política (RLS falla cerrado sin tenant fijado), no cruzando dos empresas reales.
- **El servidor de desarrollo del motor es de un solo hilo**, así que buena parte de las condiciones de carrera hoy no son explotables — pero esa seguridad es accidental, no diseñada, y desaparece al migrar a un servidor WSGI real.
- **`sn_onu` no cubre a todos los clientes**: el diagnóstico por SmartOLT depende de esa llave, y para quien no la tenga cargada el camino alternativo es preguntar por las luces del equipo.
- **TR-069 está habilitado en una fracción mínima de las ONUs**, así que la herramienta de dispositivos conectados casi nunca aplica.
- **Una sola clave de API para WispHub**: la separación por área es nuestra, no de WispHub, que ve todas las consultas como del mismo usuario del staff.
