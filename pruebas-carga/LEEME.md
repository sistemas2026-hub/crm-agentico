# Prueba de carga de Dexter

Simula a la gente que usa Dexter **al mismo tiempo**, haciendo lo mismo que hace su navegador o su teléfono, con la misma frecuencia, y dice si el servidor aguanta.

## Qué simula

Tres tipos de persona. Cada una repite lo que hace su pantalla real, con el intervalo que tiene el código:

| Persona | Qué pide | Cada cuánto | De dónde sale el intervalo |
|---|---|---|---|
| **Oficina** (Bandeja) | La lista de chats | 8 s | `conversaciones/+layout.svelte` |
| | El chat que tiene abierto | 5 s | `conversaciones/[id]/+page.svelte` |
| | Las notificaciones | 45 s | `lib/stores/notifications.svelte.js` |
| **Supervisor NOC** | Programación en vivo | 15 s | `supervisor-noc/programacion/+page.svelte` |
| | El Pulso del NOC | 60 s | `lib/supervisor/ui/PulsoDelNoc.svelte` |
| **Técnico** (app de campo) | Su lista de trabajos y notificaciones | 2 min | `core/sync/envio_automatico.dart` |
| | Su ubicación (solo con `CARGA_ESCRIBE=si`) | 90 s | `core/ubicacion/compartir_ubicacion.dart` |

Cada persona entra a su pantalla, se queda 5 minutos sondeando y vuelve a entrar. Cada una arranca en un momento distinto, como pasa en la realidad.

**Lo que NO simula:**
- **Los mensajes de WhatsApp que entran al motor.** Cada uno llama a OpenAI (cuesta) y el motor le **contesta** al número por Meta: contra un motor real, la prueba le escribiría a teléfonos de verdad. Eso va en una segunda etapa, contra un motor con Meta y el modelo simulados.
- **La subida de fotos de la app.**

## Lo que se niega a hacer

- **Correr contra producción sin avisar.** Si el dominio es de producción, pide `-e CONTRA_PRODUCCION=si-entiendo`. La lista de dominios está en `dexter.js`; los nuevos se agregan con `-e HOSTS_PRODUCCION=app.dexter...,api.dexter...`.
- **Escribir en producción.** Las ubicaciones falsas aparecerían en el mapa del Supervisor como si fueran de los técnicos.
- **El perfil `estres` en producción.** Está hecho para encontrar dónde se rompe.
- **Seguir si el servidor ya cayó.** Si más del 10 % de los pedidos fallan durante 30 s, la prueba se corta sola.

## Antes de correr

1. **Cuentas.** Copiar `cuentas.ejemplo.json` a `cuentas.json` y poner cuentas **del servidor contra el que se prueba**:
   - Oficina: cualquier usuario de la Bandeja.
   - Supervisor: un rol ADMIN, SUPERVISOR u OPERACIONES.
   - Técnico: un usuario de la app de campo.

   Alcanza con una cuenta por tipo: varias personas simuladas pueden usar la misma. `cuentas.json` no va al repositorio (está en `.gitignore`).
2. **k6.** No hace falta instalarlo: se corre con Docker (ver abajo).
3. **Cuánta gente hay hoy.** Por defecto: 6 de oficina, 2 supervisores y 10 técnicos. Se cambia con `-e OFICINA=8 -e SUPERVISORES=2 -e TECNICOS=12`. Los perfiles multiplican esos números.

## Perfiles

| Perfil | Qué hace | Dura |
|---|---|---|
| `humo` | Una persona de cada tipo. Sirve para ver que el script funciona contra ese servidor | 1 min |
| `normal` | La gente de hoy | ~12 min |
| `doble` | El doble de gente: la tesis de un ISP con el doble de clientes | ~14 min |
| `estres` | Sube por escalones hasta 10 veces la gente de hoy, para ver **dónde** se rompe. No corre en producción | ~25 min |

## Cómo se corre

Desde la carpeta `pruebas-carga/` (Git Bash):

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/carga" -w /carga grafana/k6:1.0.0 run \
  -e FRONT=https://staging.dexter... \
  -e API=https://api-staging.dexter... \
  -e PERFIL=humo \
  dexter.js
```

Siempre `humo` primero. Si da verde, `normal`; después `doble`; y `estres` solo en staging.

**Mientras corre, en el servidor** (por SSH, en otra ventana):

```bash
bash vigilar.sh
```

Deja dos CSV: uno con la CPU y la memoria de cada contenedor, y otro con las conexiones a la base. k6 dice **cuánto** tardó cada pedido; esto dice **por qué**.

## Cómo se lee el resultado

Al terminar imprime un resumen en castellano y lo guarda en `resultados/`, también en JSON. Ejemplo:

```
Tiempo de respuesta (p95 = el 95 % tardó menos que esto):
  sondeo  mediana   180 ms  p95    640 ms  máx   2100 ms  meta p95 < 1500 ms  OK
  pagina  mediana   900 ms  p95   2400 ms  máx   4800 ms  meta p95 < 3000 ms  OK
```

- **p95**: el tiempo dentro del cual respondió el 95 % de los pedidos. Es el que cuenta. La mediana engaña: puede estar bien mientras uno de cada veinte pedidos tarda diez segundos.
- **Metas**:
  - un sondeo, en menos de 1,5 s;
  - una página, en menos de 3 s;
  - un pedido de la app, en menos de 2 s;
  - menos de 1 % de errores.
- **Sesiones caídas**: cuántas veces el servidor mandó a `/login`. Si no es 0, el problema es la sesión, no la velocidad.
- **Por pantalla**: cuál es la lenta. Ahí está lo primero que hay que arreglar.

**Dónde mirar según lo que pase:**

| Síntoma | Probable causa | Qué se ajusta |
|---|---|---|
| La CPU del `backend` cerca de 100 % y los tiempos suben | Pocos procesos para Django | `GUNICORN_WORKERS` / `GUNICORN_THREADS` en Dokploy (hoy 3 × 4 = 12 pedidos a la vez) |
| Muchas conexiones «en espera» o cerca del máximo en `base-*.csv` | Se acaban las conexiones a la base | `DB_POOL_MAXIMO` del motor, o el límite del pooler de Supabase |
| La Bandeja lenta y el `motor` alto | El motor atiende 16 pedidos a la vez (1 proceso × 16 hilos) | `--threads` del motor en el compose |
| Errores 502/504 | Un contenedor se reinició o se quedó sin memoria | `docker ps` y la memoria del VPS |
| Todo sube parejo con la CPU del servidor al tope | El VPS es chico para esa cantidad de gente | Más CPU o separar la base del servidor de la aplicación |

## Dónde correrla

- **Staging**: siempre que exista. Es donde corresponde, sobre todo `estres`.
- **Producción**: solo `humo`, `normal` o `doble`, fuera de horario y con alguien mirando `vigilar.sh`. Es el mismo servidor que atiende a los clientes: si se satura, lo sienten.
- **Un laboratorio local** sirve para comprobar que el script funciona y para comparar una rama contra otra, no para sacar conclusiones de capacidad: tu PC no es el VPS.

## El laboratorio local

`laboratorio.sh` levanta Dexter completo y aislado en tu PC, con contenedores `cargalab-*` en los puertos 55432, 58000 y 53000. Incluye:
- base nueva armada por el ledger;
- backend con gunicorn;
- motor con 1 proceso y 16 hilos, con WispHub en modo simulado;
- frontend compilado como en producción;
- una empresa con 6 cuentas de prueba y 600 chats de 25 mensajes.

```bash
bash pruebas-carga/laboratorio.sh arriba    # ~10 min la primera vez
bash pruebas-carga/laboratorio.sh humo      # o normal, doble, estres
bash pruebas-carga/laboratorio.sh abajo
```

Las contraseñas de prueba se generan al azar en `pruebas-carga/.laboratorio/`, que no va al repositorio.

## Lo que se midió en el laboratorio (24/11/2026)

En una PC de desarrollo, con el código de producción de ese día (`67d0f9e6`). Perfil `estres`, que llegó a **180 personas a la vez**: 60 de oficina, 20 supervisores y 100 técnicos, diez veces la base de hoy.

| | Resultado |
|---|---|
| Pedidos | 18.994 en 25 min, 0 % de error, 0 sesiones caídas |
| Sondeos (p95) | 156 ms |
| Páginas (p95) | 283 ms |
| App de campo (p95) | 40 ms |
| Lo más lento | la lista de la Bandeja (mediana 119 ms) y abrir Programación (194 ms) |
| Lo que más trabajó | **la base de datos**: picos de 1,6 núcleos; backend 1,2; motor 0,65; frontend 0,45 |
| Conexiones a la base | 14 como máximo |

**Qué quiere decir:** con esta mezcla de uso, lo primero que se va a llenar es la base, no los procesos de la aplicación. En el VPS, la base de Supabase comparte máquina con todo lo demás, así que el número que importa es la CPU total del servidor durante la prueba. Esa cifra sale de correr `vigilar.sh` allá.

**Hallazgo:** cada sondeo de notificaciones del navegador cuesta **dos** pedidos. Pide `/api/notifications/?limit=…` con barra final y SvelteKit le contesta 308 hacia la ruta sin barra. Se arregla quitando la barra en `lib/stores/notifications.svelte.js`. La prueba hace los dos pedidos, como el navegador, y el 308 sale aparte como `notificaciones-308`.
