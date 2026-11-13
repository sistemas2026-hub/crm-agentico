# Objetivo · Cada empresa ve cuánto trabajo le resolvió Dexter

> Abierto el 30/10/2026. Estado: **abierto**.
> El **qué** y el **por qué** viven en [PRD.md §2 y §8.17](../../PRD.md) (Ola 1, decisión 1) y no se
> repiten acá: esta ficha es el contrato de ejecución. Si difieren, manda el PRD.

## Qué significa terminado

Una persona de la empresa abre una pantalla y ve, para el período que elija,
las seis métricas de PRD §2 calculadas por el motor sobre conversaciones reales,
y cada número se puede rastrear hasta las filas que lo producen.

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| C1 | Las seis métricas se calculan en el motor contra **PostgreSQL real** | `py -3.13 tests/test_tablero_capacidad.py` con `TEST_DATABASE_URL` → verde, salida pegada. Siembra conversaciones con cada desenlace (cerrada por la IA, tomada, intervenida, con acción aprobada, con recontacto a 48 h y a 96 h, con reinicio confirmado con y sin visita posterior) y afirma el número exacto de cada métrica |
| C2 | Solo cuentan los canales reales | La misma prueba siembra conversaciones de `web` y del simulador, y afirma que no mueven ningún número. Mutación: quitar el filtro `canales.REALES` → la prueba falla (pegar la salida en rojo) |
| C3 | Una conversación con intervención humana **nunca** cuenta como resuelta sin persona | Casos: una persona escribió (`messages.origen = 'humano'`), tomó el caso, intervino sin escalada, o aprobó una acción. Los cuatro → no resuelta. Mutación: ignorar `acciones_propuestas` → falla |
| C4 | La fecha de corte se declara | La respuesta trae `desde` ≥ la fecha en que existe `messages.origen` (16/09/2026) y lo dice; un período anterior devuelve el aviso, no un número |
| C5 | Minutos por conversación y por visita son configuración de la empresa | `TenantConfig.capacidad` con validación; `py -3.13 tests/test_editor_config.py` verde. Sin minutos declarados, *minutos ahorrados* devuelve `null` con motivo, **nunca** un default. *Era "por tipo de caso": una conversación no tiene un tipo confiable, así que son dos números (30/10/2026)* |
| C6 | La tasa de escalada existente filtra por canal | `persistencia.tasa_escalamiento` con el mismo filtro; prueba que lo afirme |
| C7 | La cadena completa llega a la pantalla | Una prueba del `+page.server.js` de la pantalla nueva que recibe la respuesta del endpoint y afirma que las seis claves llegan con el nombre que escribe el motor (CLAUDE.md §6: `requiere_noc` y `estado_nuevo` se perdieron en esa capa) |
| C8 | El núcleo sigue sin conocer a nadie | `py -3.13 tests/test_nucleo_sin_tenants.py` verde |
| C9 | Corre en la topología real | Después del deploy, el endpoint responde en producción para `rapilink` con un período de 7 días. Lo mide quien despliega; no se hace con capturas contra producción |
| C10 | `auditor-independiente` y `revisor-de-pii` corrieron | Hallazgos resueltos o anotados en `SPEC/auditorias/` con motivo. El tablero devuelve **agregados**: ninguna fila, nombre ni número de cliente |

## Restricciones

- **NO push** — push a `fix/integracion-wisphub` es deploy a producción.
- **NO escribir `tenant_config`** — cada guardado parte la medición ON/OFF. Los minutos por caso se agregan al esquema y al YAML semilla; cargarlos es un paso de despliegue aparte.
- **NO correr los casos dorados completos** — no tocan prompt ni catálogo.
- **El modelo no calcula ningún número** (PRD §12.5). Todo sale de SQL o Python.
- **Agregados, nunca filas** hacia la pantalla. Es una lectura de toda la base de conversaciones de una empresa: aislada por `app_backend` + `app.current_tenant` como cualquier otra.

## Qué NO hacer

- **No inventar el contrafactual.** "Visitas evitadas" se define como en PRD §2 (reinicio confirmado sin visita en 7 días) y la pantalla lo dice con esas palabras. No se presenta como certeza.
- **No reconstruir datos anteriores al 16/09/2026.** `control` no se rellenó hacia atrás; un número sobre ese período sería inventado.
- **No conectar todavía el tablero a la autonomía.** Eso es la Ola 3; acá solo se mide.

## Lo medido, que define el tamaño

```
Ya se guarda:  conversations.control / control_motivo / cerrada_por_tipo / atendida_manual / tomada_por
               relevo_eventos (intervencion, tomada, cerrada)       messages.origen (desde 16/09/2026)
               verificaciones_accion (ACCION_CONFIRMADA)            tool_calls (agendar_visita_*)
               acciones_propuestas.estado / revisado_en              encuestas WhatsApp (202610281600)
No se guarda:  minutos humanos por tipo de caso (config nueva)
               conversations.cerrada_en (sale de relevo_eventos 'cerrada'; verificar que todo cierre lo deje)
Única cifra de resultado en pantalla hoy: tasa de escalada en /agentes, sin filtro de canal.
```

## Bloqueos

Ninguno para arrancar. *Satisfacción* depende de que la encuesta de WhatsApp salga
a todos y no solo a los números de prueba (`solo_a`): mientras tanto la pantalla
muestra la muestra y su tamaño.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 30/10/2026 | Decisión registrada (PRD §2, §8.17), datos existentes medidos | Ejecutar | 3f624a52 |
| 30/10/2026 | **C1–C8 en verde.** `test_tablero_capacidad_base.py` contra PostgreSQL (base efímera del ledger): todas las métricas con su número exacto; mutaciones cazadas: sin filtro de canal (C2), ignorar acciones (C3), tasa de escalada sin filtro (C6). C4 corte con aviso, C5 null sin default, C7 `capacidad-servidor.test.js` 6/6 y sin errores de tipos, C8 guarda del núcleo verde | C9 y C10 | 20687706 |
| 30/10/2026 | **C10 corrió**: `revisor-de-pii` sin fugas; `auditor-de-frontera` y `auditor-independiente` con hallazgos, resueltos o anotados en PRD §8.17 ("Lo que cambió la auditoría"). Dos inflaban el tablero a favor de Dexter (visita del código fuera de `tool_calls`, ventanas incompletas). La prueba con base pasa a 32 comprobaciones y caza 7 mutaciones. Los tres números que declara la empresa se editan desde `/capacidad`; `cli/cargar_claves.py` sube lo nuevo sin pisar la base | C9: correr en la topología real tras el deploy, con los pasos de PRD §8.17 | (este commit) |
