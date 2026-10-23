# Relevo · 21/10/2026 · Labores, plantillas y «el Supervisor despacha solo»

> **Si te dijeron «toma contexto»:** leé este archivo entero, después las dos
> fichas que nombra (§3) y recién ahí `CLAUDE.md` §1 en el orden de siempre.
> Este relevo NO reemplaza la jerarquía de `CLAUDE.md`: es el atajo para
> retomar lo que estaba en marcha. Ante una contradicción, ganan las fichas y,
> por encima, `CLAUDE.md`.

Escrito por la sesión que trabajó del 19 al 21/10/2026 en el worktree
`C:/wt-desp` de otra PC. El usuario habla en español, quiere respuestas cortas
con el siguiente paso primero (modo TDAH) y decide cada push.

---

## 1 · Estado en producción al cerrar

Producción = el commit que trae este archivo (rama `fix/integracion-wisphub`).
Medilo con `git fetch` antes de afirmarlo. Lo que entró en estos dos días, en
orden, con lo que el usuario ve:

| Commit | Qué cambió para el usuario |
|---|---|
| `b1c75518` | Labores por empresa, fase 1: tabla `campo_labor` sembrada (instalación, correctivo, trabajos) en las 8 empresas. Sin cambio visible |
| `6b7b5115` | Plantillas: botón **«+ Nueva plantilla»** con nombre, labor, plazo y **asuntos** al crearla; «Guardar» en el editor; la lista muestra los asuntos |
| `e7d6250f` | **Una sola regla elige la plantilla de un caso** (`campo.plantillas.plantilla_del_caso`): el asunto, salvo labor medida; si no, la única de la labor; si no, ninguna y dice por qué. La usa Despacho |
| `4beab787` | **Horario de las cuadrillas** en Cuadrillas, aparte del de atención al cliente (zona, días, horas, feriados, **hora de corte**). Sin él, el Supervisor no arma solo |
| `26dd2508` | **Feriados que se trabajan**: el día hábil anterior el Supervisor deja una propuesta con la cola contra la capacidad; se trabaja escribiendo el horario en la línea del feriado (`AAAA-MM-DD 07:00-12:00 Nombre`). Habilidad **H-20** |
| `9f6eb8f5` | El **chat del Supervisor** en todas las pestañas de Supervisor NOC (layout), sin cortarse al cambiar |
| `c325818c`, `c2aac032` | **«Ver qué armaría el Supervisor»** en Cuadrillas → El día (no escribe nada). El Supervisor **escribe solo en el chat** las propuestas de feriado; la burbuja muestra un contador |
| `a10eb663` | Arreglos que mostró la vista previa: usa el día elegido, la gente de las jornadas ya armadas, nombra los **barrios sin zona**, y el armado no cruza labores |
| `bebc2f90` | **«Según la cantidad»**: las cuadrillas de una zona se reparten según los casos de cada labor (reemplaza la regla del 17/10). **Lo usa también la madrugada** |

**Lo primero a mirar al retomar:** la corrida de la madrugada del día
siguiente al deploy de `bebc2f90` (03:00 Bogotá). En el backend, solo lectura:
`ConfiguracionDeReparto.objects.get(org__name="Rapilink").ultima_corrida`
tiene que tener la fecha de ese día (se escribe al FINAL del ciclo, solo si
terminó entero), y en Cuadrillas → El día las jornadas tienen que verse
repartidas según la cantidad.

---

## 2 · Lo que tiene que hacer el usuario (datos, sin código)

1. **Barrios sin zona.** La vista previa mostró **21 casos** de Despacho con barrio
   sin zona: nunca le llegan a una cuadrilla. Ahora la vista previa los nombra;
   se cargan en Cuadrillas → Zonas operativas → Elegir barrios.
2. **Plazo en cada plantilla** (Plantillas → Editar → «Plazo para hacerlo
   (días)»). Hasta el 21/10 las tres decían «sin plazo», y por eso «Para cuándo»
   salía vacío en Despacho.
3. **Delegar el armado** en el chat del Supervisor: «armá la jornada del día de
   cada cuadrilla». El horario de las cuadrillas ya está cargado (L-V 7–17,
   sábado 7–12, corte 14:30, feriados de Colombia hasta fin de 2027).

---

## 3 · Las dos fichas (el contrato; leelas del disco)

- **`SPEC/objetivos/supervisor-arma-la-jornada.md`** — la principal. Decisiones del
  usuario del 21/10 (pasos 7 y 9 automáticos, hora de corte, corte de red = una
  orden por puerto, cupo lleno → mañana, mover solo antes de que arranque el día,
  instalaciones nuevas sin copiar la ficha del cliente ficticio, aviso push al
  técnico, horario de las cuadrillas, feriados, «según la cantidad»), el **plan
  del arquitecto en fases 2.0–3.1** con sus hallazgos verificados y la bitácora.
- **`SPEC/objetivos/labores-propias-por-empresa.md`** — labores por empresa (D1–D13).
  F1 y la regla de plantilla están hechas; D11 (casillas) quedó **reemplazada**
  por pedido directo del usuario: los asuntos se escriben en la plantilla.

---

## 4 · Lo que sigue, en orden

Estimaciones del arquitecto; cada fase arranca en sombra y se despliega sola.

1. **2.1 · Extracciones sin cambio de conducta** (~1 día): `labor_del_caso` (de
   `demanda_de_despacho`), `orden_desde_el_caso` (de `CrearOrdenView`), una sola
   «orden viva del caso» (hoy hay 3 copias con 2 definiciones).
2. **La labor por asunto en la demanda** (F3 de labores, 1,5–2 días): que la
   jornada y la orden decidan la labor con la misma regla. **Antes**, el informe
   de solo lectura de cuántos casos cambian (la madrugada está encendida).
   Coordinar con quien sea dueño de `operaciones/armado_de_jornadas.py`.
3. **2.2 · El reparto se corrige** (~1–1,5 días): hoy **ignora la prioridad y
   `programada_para`** (una orden para mañana se reparte hoy), decide «empezada»
   por un evento que **nadie escribe** (`trabajo_iniciado`; lo real es
   `iniciada_en`), y `RepartoView.post` se extrae a `campo/reparto.py::publicar`.
   Cambia el botón humano: decirlo.
4. **2.3 · El Supervisor crea las órdenes** (~2,5–3 días), con la prioridad por
   tiempo de espera (creación + plazo de la plantilla) calculada en código.
5. **3.1 · El Supervisor publica** (~1,5–2 días) y el **push al técnico**.

Agentes obligatorios en 2.2, 2.3 y 3.1: `auditor-de-frontera`; en 2.3,
`revisor-de-pii` (datos del cliente en la orden, y el hueco `MOTOR_TENANT` de la
ficha); `auditor-independiente` en cada fase; `guardia-de-release` antes de cada
push con migraciones.

Pedido abierto del usuario, sin decidir: **qué otras propuestas** además de los
feriados quiere recibir por el chat (hoy solo `feriado_por_decidir`, en
`operaciones/aviso_al_chat.py::TIPOS_QUE_SE_AVISAN`).

---

## 5 · Cómo se trabajó (y las trampas que costaron tiempo)

- **Worktree corto sobre origin**, nunca la copia principal (está cientos de
  commits atrás con archivos sueltos): `git worktree add C:/wt-x origin/fix/integracion-wisphub`
  y trabajar con HEAD separado; `git rebase origin/fix/integracion-wisphub` antes
  de cada push, mirando que no haya archivos ni migraciones en común.
- **Push = DEPLOY A PRODUCCIÓN.** El usuario lo pide explícito («haz el push»)
  en cada entrega; decírselo con esa palabra. Verificar con
  `curl https://agent.rapilinksas.co/_app/version.json` (~3 min). **Un deploy que
  no toca el frontend no cambia ese sello**: la prueba es el backend.
- **`SPEC/DEXTER_ESTADO_ACTUAL.md` no se edita**: un solo escritor (la sesión de
  `integrar-centro-mando`). Se le entregan hashes (§6).
- **Pruebas del backend contra Postgres real con un rol que el RLS ata**
  (`crm_t`, `nosuperuser nobypassrls`): Postgres 16 efímero en la red del compose
  local y un contenedor de un solo uso con la imagen del backend montando el
  worktree; `MSYS_NO_PATHCONV=1`, `TEST_DATABASE_URL=postgres://crm_t:t@<pg>:5432/crmt`,
  `--reuse-db` (la primera vez, o con migraciones nuevas, `--create-db`).
- **Después de reiniciar la PC**: encender el Postgres de pruebas **y Redis**. Sin
  Redis, `test_m09f_gobernanza::test_el_ciclo_completo_por_http_no_llama_a_nadie`
  y `test_m09l_ciclo_integrado::test_api_el_ciclo_manual_devuelve_resumen_y_detalle`
  dan 503 y parecen rojos nuevos.
- **Regresión**: `pytest campo operaciones business_hours` tiene ~94 rojos
  previos. No se compara contra un número: se corre **origin con la misma receta**
  y se comparan los NOMBRES de los rojos.
- **Archivos en CRLF** en el worktree (autocrlf): un parche por anclas tiene que
  usar el fin de línea del archivo. Los heredoc largos de Bash convierten `\n` en
  saltos reales: los parches van como script escrito con la herramienta de
  archivos, con simulacro y anclas contadas.
- **`svelte-check`**: 161 errores en origin al 21/10. Con una ruta nueva hay que
  correr antes `npx svelte-kit sync`, si no aparecen errores falsos de `./$types`.
  Nunca `pnpm check` con Docker arriba.
- **Mutaciones**: cada cambio de esta sesión se cerró rompiéndolo a propósito y
  comprobando que una prueba lo detecta (una sobrevivió a la primera y originó
  una prueba nueva). Los scripts eran desechables; el método es el de §6 de
  `CLAUDE.md`.
- **Guardas de gobernanza que piden declarar a mano**: toda ruta nueva de
  `operaciones/urls.py` va al inventario de `test_m09f_gobernanza.py`, y toda
  habilidad nueva del Supervisor a las guardas que cuentan habilidades (con la
  autorización del usuario escrita).

---

## 6 · Para el dueño del estado (`integrar-centro-mando`)

Una línea por cierre, para `SPEC/DEXTER_ESTADO_ACTUAL.md`:

- Labores por empresa F1 desplegada: `b1c75518`.
- Plantilla con asuntos desde un botón: `6b7b5115`. Regla única de plantilla: `e7d6250f`.
- Horario de las cuadrillas: `4beab787`. Feriados que se trabajan + H-20: `26dd2508`.
- Chat del Supervisor en todas las pestañas: `9f6eb8f5`. Vista previa del armado y aviso en el chat: `c325818c`, `c2aac032`.
- Arreglos de la vista previa y «según la cantidad» (cambia la madrugada): `a10eb663`, `bebc2f90`.
