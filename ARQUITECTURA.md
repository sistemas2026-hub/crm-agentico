# Estructura del proyecto

> Entregable 3 de 9. Agosto 2026.

## La única regla

El proyecto se parte en dos zonas, y toda la arquitectura depende de que no se mezclen:

| Zona | Qué es | Puede conocer un cliente |
|---|---|---|
| `nucleo/` | El motor | **Nunca** |
| `tenants/` | Configuración por empresa | Es su razón de existir |

Dar de alta un ISP nuevo es: fila en `tenants` (tabla), archivo en `tenants/` (carpeta), cargar sus documentos. **Cero cambios en `nucleo/`.**

Si al escribir código en el núcleo aparece la necesidad de distinguir un cliente, no se resuelve con un `if`: significa que **falta un campo en la configuración**.

### Y no depende de que alguien se acuerde

```
py -3.13 tests/test_nucleo_sin_tenants.py
```

Lee los slugs de `tenants/*.yaml` y falla si alguno aparece bajo `nucleo/`. También caza las formas de colar lógica por cliente sin nombrarlo: ramas por tenant, comparaciones contra slug literal, URLs de servicios concretos embebidas.

Ignora comentarios y docstrings —documentar por qué existe una regla no es violarla— pero **no** las cadenas dentro del código, que es justamente donde se escondería un slug.

Cuando falla, no se agrega una excepción. Se mueve el comportamiento a la configuración.

## Mapa

```
nucleo/                    EL MOTOR — genérico, sin clientes
  config/                  carga y validación de tenant.config.yaml
  seguridad/               listas blancas, permisos por rol, autenticación
  herramientas/            tipos genéricos: http · agregado · sql · batch
  ingesta/                 fragmentación, contextualización, versionado
  recuperacion/            búsqueda híbrida, ensamblado del prompt
  modelo/                  cliente LLM, selección por canal/rol
  canales/                 whatsapp, web
  persistencia/            repositorios sobre Supabase
  observabilidad/          auditoría, consumo, Langfuse

tenants/                   DATOS por empresa — sin código
  tenant.config.example.yaml    plantilla de alta
  rapilink.config.yaml          primer despliegue

supabase/                  migraciones SQL
cli/                       utilidades operativas
evaluacion/                sets dorados por tenant
tests/                     incluye la guarda del núcleo
```

**`tenants/` no contiene código a propósito.** El validador vive en `nucleo/config/schema.py`: la configuración es dato, y lo que la interpreta es motor.

## Dónde aterriza lo que ya existía

El sistema actual se **absorbe**, no se rescribe. Casi todo era ya configuración disfrazada de código:

| Hoy | Destino | Naturaleza |
|---|---|---|
| `AGREGACIONES` (filtros verificados) | `tenants/rapilink.config.yaml` | ✅ ya portado |
| Listas blancas por área | `roles.*.campos_permitidos` | ✅ ya portado |
| `AREAS` (4 roles) | `roles` | ✅ ya portado |
| Motor de agregación | `nucleo/herramientas/agregado.py` | Código genérico |
| `filtrar_campos()` | `nucleo/seguridad/listas_blancas.py` | Código genérico |
| `registrar_auditoria()` | `nucleo/observabilidad/auditoria.py` | Código genérico |
| `construir_system()` | `nucleo/recuperacion/prompt.py` | Código genérico |
| `cli/banco_pruebas.py` | semilla de `evaluacion/` | Casos → tabla |
| `cli/informe_materiales.py` | herramienta tipo `batch` | Ya declarada en config |

`soporte_wisphub.py` sigue funcionando mientras tanto. La migración es incremental: cada pieza que se mueve al núcleo se valida contra el banco de pruebas antes de retirar la anterior.

## Variables de entorno

Ninguna vive en los YAML. La configuración solo guarda **nombres** (`auth_ref: WISPHUB_API_KEY`); el validador rechaza el archivo si detecta un valor con pinta de credencial.

```
WISPHUB_API_KEY            clave del ISP
WISPHUB_BASE_URL
WISPHUB_MODO_REAL

VITE_SUPABASE_URL          proyecto
VITE_SUPABASE_ANON_KEY     pública por diseño — protegida por RLS
SUPABASE_SERVICE_ROLE_KEY  ⚠️  solo migraciones (ver abajo)

DATABASE_URL               ⏳ pendiente: conexión como rol app_backend
```

### ⚠️ Sobre `SUPABASE_SERVICE_ROLE_KEY`

Ese rol tiene `BYPASSRLS`: **las políticas de aislamiento no se evalúan para él**. Comprobado en la prueba del esquema — como superusuario se ven los datos de todos los tenants.

Por eso el backend **no** debe usarlo para consultar datos de tenant. Se conecta como `app_backend`, que sí respeta RLS, fijando `set local app.current_tenant` en cada petición. `SUPABASE_SERVICE_ROLE_KEY` queda para migraciones y mantenimiento.

Falta agregar `DATABASE_URL` con esa conexión.
