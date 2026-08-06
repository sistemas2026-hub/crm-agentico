# crm-agentico

Asistente interno de IA para ISPs (multi-tenant), primer despliegue: **Rapilink**. Deja que un colaborador pregunte en lenguaje natural sobre sus sistemas (hoy: WispHub) según su área.

## Lectura obligatoria, siempre, sin que se pida

Antes de proponer o hacer cualquier cambio, lee completos:

- [PRD.md](PRD.md) — producto, requisitos, decisiones y su motivo. Fuente de verdad de **qué** se construye y **por qué**.
- [ARQUITECTURA.md](ARQUITECTURA.md) — estructura del repo y la regla de separación núcleo/tenant. Fuente de verdad de **cómo** se organiza el código.

Estos dos archivos cambian seguido y son la fuente de verdad — no un resumen de este archivo. Léelos del disco en cada sesión, no asumas que el contenido sigue igual a la última vez. Si `git log -5 -- PRD.md ARQUITECTURA.md` muestra commits que no reconoces, son cambios de otro colaborador: revísalos antes de tocar nada relacionado.

## La única regla de arquitectura

`nucleo/` = motor genérico, nunca conoce un cliente. `tenants/` = configuración por empresa, sin código. Ver detalle en ARQUITECTURA.md. Verificar con:

```
py -3.13 tests/test_nucleo_sin_tenants.py
```

## Decisiones que no hay que redescubrir

- **El modelo compone, el código calcula** (PRD §12.5): ninguna consulta agregada le pide al modelo sumar, contar o promediar filas. Python calcula; el modelo traduce lenguaje a parámetros y redacta el resultado.
- **Seguridad en dos capas** (PRD §7.4): el filtro de PII y la confirmación de acciones sensibles viven en código, fail-closed. El prompt es guía, nunca la garantía.
- **La documentación de la API de WispHub es una hipótesis** — nunca una fuente de verdad. Antes de usar un filtro nuevo, cargar la skill `wisphub-api` y verificar con el método del valor imposible.
- DeepSeek (`deepseek-v4-flash`) está aprobado para todos los roles, incluida PII, por la autorización de tratamiento que firma el cliente (Ley 1581 art. 26) — ver PRD RNF-01 antes de cuestionar por qué datos de cliente salen a una API externa.
- Las respuestas crudas de la API de WispHub **no se persisten** en Supabase (traen contraseñas, GPS, cédula). La auditoría (`tool_calls`) guarda solo metadatos.

## Comandos útiles

```
py -3.13 tests/test_nucleo_sin_tenants.py   # guarda de arquitectura
py -3.13 cli/banco_pruebas.py               # compara modelos contra el prompt real
py -3.13 cli/sondear_api.py                 # descubre endpoints de WispHub (solo lectura)
```
