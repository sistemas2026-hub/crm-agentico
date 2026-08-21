# crm-agentico

Asistente interno de IA para ISPs (multi-tenant), primer despliegue: **Rapilink**. Deja que un colaborador pregunte en lenguaje natural sobre sus sistemas (hoy: WispHub) según su área.

## Lectura obligatoria, siempre, sin que se pida

Antes de proponer o hacer cualquier cambio, lee completos:

- [PRD.md](PRD.md) — producto, requisitos, decisiones y su motivo. Fuente de verdad de **qué** se construye y **por qué**.
- [ARQUITECTURA.md](ARQUITECTURA.md) — estructura del repo y la regla de separación núcleo/tenant. Fuente de verdad de **cómo** se organiza el código.

Y antes de tocar el servidor, el despliegue o la conexión a la base:

- [DESPLIEGUE.md](DESPLIEGUE.md) — cómo se pone a andar en el VPS, qué falta, y los errores que ya costaron tiempo una vez. Consultar su sección de diagnóstico **antes** de depurar un fallo de conexión o de despliegue: varios de esos errores señalan a la causa equivocada.

Estos dos archivos cambian seguido y son la fuente de verdad — no un resumen de este archivo. Léelos del disco en cada sesión, no asumas que el contenido sigue igual a la última vez. Si `git log -5 -- PRD.md ARQUITECTURA.md` muestra commits que no reconoces, son cambios de otro colaborador: revísalos antes de tocar nada relacionado.

## La única regla de arquitectura

`nucleo/` = motor genérico, nunca conoce un cliente. `tenants/` = configuración por empresa, sin código. Ver detalle en ARQUITECTURA.md. Verificar con:

```
py -3.13 tests/test_nucleo_sin_tenants.py
```

## Esto es SaaS multi-tenant: diseñar para muchas empresas, no para Rapilink

Rapilink es el primer despliegue, no el único que va a existir. Toda decisión de diseño asume que **se van a conectar muchas empresas**, cada una con sus propios valores — no solo Rapilink con los suyos hardcodeados.

La consecuencia concreta: un dato que varía por empresa (el subdominio de una API externa, un ID de cuenta, cualquier config que no es igual para todo el mundo) se modela como **configuración editable desde la interfaz y persistida en la config del tenant** — nunca como un valor fijo en código, ni en un YAML que solo un desarrollador sabe editar. "Hoy solo hay un tenant" no es excusa para hardcodear: la próxima empresa que se conecte no debería necesitar una sesión de código para algo que ya se resolvió una vez. Ver el patrón ya construido para esto: `TenantConfig.variables_tenant` + `Herramienta.base_url_ref` (`nucleo/config/schema.py`) — mismo espíritu que `auth_ref` para secretos, pero para datos que no son secretos y aun así varían por empresa. `nucleo/config/editor.py` ya persiste config por tenant en base de datos (`asistente.tenant_config`), versionada — el YAML en `tenants/*.yaml` es solo la semilla inicial, no la fuente de verdad una vez cargado.

Esto no es una sugerencia de "buena práctica" en abstracto: nace de una corrección directa de un colaborador después de que se declarara un dato de empresa (el subdominio de SmartOLT) como fijo en el YAML "porque hoy solo hay un tenant y cambiarlo es más trabajo". No repetir ese razonamiento.

## Antes de dar por bueno un cambio de prompt, catálogo o modelo

```
py -3.13 cli/evaluar.py rapilink
```

Casos dorados (`evaluacion/<slug>.casos.yaml`) contra el motor **real**. Afirman sobre la **traza** —qué herramientas se llamaron, a qué área se derivó, si hubo errores, qué no puede aparecer en la respuesta— y nunca sobre la redacción: el modelo dice lo mismo de diez formas y un test que exige una frase exacta falla por lo que no importa.

Nace de una lección cara (14/08/2026): tres bugs estuvieron rotos horas —una herramienta devolviendo un *error* donde debía haber un dato, un veredicto que no se calculaba, una precondición imposible de cumplir— y **ninguno se veía leyendo la respuesta**. Los tres se ven en la traza. Validar a mano abriendo el simulador no los detecta.

Cuando algo falle en producción, agregarlo al set con lo que *debería* haber pasado: así crece con fallas reales, no con casos imaginados, y cada bug arreglado queda con su guarda.

## Decisiones que no hay que redescubrir

- **El modelo compone, el código calcula** (PRD §12.5): ninguna consulta agregada le pide al modelo sumar, contar o promediar filas. Python calcula; el modelo traduce lenguaje a parámetros y redacta el resultado.
- **Seguridad en dos capas** (PRD §7.4): el filtro de PII y la confirmación de acciones sensibles viven en código, fail-closed. El prompt es guía, nunca la garantía.
- **La documentación de la API de WispHub es una hipótesis** — nunca una fuente de verdad. Antes de usar un filtro nuevo, cargar la skill `wisphub-api` y verificar con el método del valor imposible.
- DeepSeek (`deepseek-v4-flash`) está aprobado para todos los roles, incluida PII, por la autorización de tratamiento que firma el cliente (Ley 1581 art. 26) — ver PRD RNF-01 antes de cuestionar por qué datos de cliente salen a una API externa.
- Las respuestas crudas de la API de WispHub **no se persisten** en Supabase (traen contraseñas, GPS, cédula). La auditoría (`tool_calls`) guarda solo metadatos.

## Comandos útiles

```
py -3.13 tests/test_nucleo_sin_tenants.py   # guarda de arquitectura
py -3.13 tests/test_editor_config.py        # guarda del editor de agentes (sin base)
py -3.13 tests/test_timeouts_modelo.py      # ninguna llamada al modelo se cuelga (sin red)
py -3.13 cli/evaluar.py rapilink            # casos dorados contra el motor real
py -3.13 cli/banco_pruebas.py               # compara modelos contra el prompt real
py -3.13 cli/sondear_api.py                 # descubre endpoints de WispHub (solo lectura)
```

## Configuración de una sola vez por máquina (cada colaborador)

Git no versiona hooks ni alias — hay que activarlos a mano una vez por copia local del repo:

```
git config core.hooksPath .githooks
git config alias.novedades '!git fetch origin && echo "--- commits nuevos ---" && git log HEAD..origin/fix/integracion-wisphub --oneline && echo "--- archivos que cambiaron ---" && git diff --stat HEAD origin/fix/integracion-wisphub'
```

`git novedades` trae del remoto (sin mezclar nada localmente) y muestra qué commits y qué archivos cambió el otro colaborador desde la última vez — para revisar antes de hacer `git pull`.
