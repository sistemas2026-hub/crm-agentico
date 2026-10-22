# M09-K — Habilidades operativas: formalización y versionado

## 1. Estado

**COMPLETADO.** 14 de 14 habilidades formalizadas.

| | |
|---|---|
| Producción | **sin cambios** |
| Efectos externos | **0** |
| Autonomía | **sin cambios** |
| Tablas creadas | **0** |
| Migraciones | **0** |
| Pruebas | **324 passed** (180 base + 144 nuevas), 0 regresiones |
| H-05 | **BLOQUEADA — D-4** |

---

## 2. Decisión D-1 aplicada

> **El código de M09 es la fuente canónica de las habilidades operativas.**

Lo que eso significó en la práctica:

| Lo que **no** se hizo | Lo que **sí** se hizo |
|---|---|
| no se creó ninguna tabla | un diccionario literal congelado en código |
| no se tocó `asistente.habilidades` | se dejó intacta, sin leerla ni escribirla |
| no se integró Motor ↔ CRM | cero imports nuevos entre ellos |
| no se modificó ningún detector | se los describe, con una prueba que verifica que la descripción no miente |

**Este documento es una VISTA del código, no la fuente.** La fuente es
[`operaciones/habilidades.py`](django-crm/backend/operaciones/habilidades.py).
Duplicar aquí las 14 fichas completas crearía la segunda definición que D-1
existe para evitar — por eso cada ficha se resume y se acompaña de su **huella**,
que permite verificar que este documento describe exactamente esa versión.

---

## 3. Catálogo de las 14 habilidades

| ID | Nombre | Tipo | Nivel | Estado | Referencia | Detector |
|---|---|---|:--:|---|---|---|
| **H-01** | Detectar caso abierto sin resolución registrada | dominio | 1 | vigente | `habilidad:H-01@1` | `_casos_abiertos_antiguos` |
| **H-02** | Evaluar completitud de datos de una orden | dominio | **0** | vigente | `habilidad:H-02@1` | `_ordenes_desincronizadas` |
| **H-03** | Determinar si una OT tiene programación vigente | dominio | 1 | vigente | `habilidad:H-03@1` | `_ordenes_sin_programar` |
| **H-04** | Detectar plan semanal sin publicar | dominio | 1 | vigente | `habilidad:H-04@1` | `_programaciones_sin_publicar` |
| **H-05** | Estimar riesgo operacional por capacidad | dominio | 1 | **bloqueada** | `habilidad:H-05@1` | `_ordenes_en_riesgo` |
| **H-06** | Detectar actividad vencida sin cierre | dominio | 1 | vigente | `habilidad:H-06@1` | `_actividades_vencidas` |
| **H-07** | Detectar actividad sin responsable | dominio | 1 | vigente | `habilidad:H-07@1` | `_actividades_sin_responsable` |
| **H-08** | Detectar actividad bloqueada y citar su causa | dominio | 1 | vigente | `habilidad:H-08@1` | `_actividades_bloqueadas` |
| **H-09** | Detectar compromiso próximo a vencer | dominio | 1 | vigente | `habilidad:H-09@1` | `_compromisos_por_vencer` |
| **H-10** | Detectar dependencia pendiente | dominio | 1 | vigente | `habilidad:H-10@1` | `_dependencias_pendientes` |
| **H-C1** | Calcular y explicar la prioridad | transversal | **0** | vigente | `habilidad:H-C1@1` | — |
| **H-C2** | Construir evidencia trazable | transversal | **0** | vigente | `habilidad:H-C2@1` | — |
| **H-C3** | Calcular la huella de la condición | transversal | **0** | vigente | `habilidad:H-C3@1` | — |
| **H-C4** | Redactar sin atribuir culpa | transversal | **0** | vigente | `habilidad:H-C4@1` | — |

**Son exactamente las 14 de M09-J.** Ninguna añadida, ninguna eliminada, los IDs
conservados.

---

## 4. Las fichas — lo que cada una fija

Cada ficha del código declara 24 campos. Aquí va lo que distingue a cada una;
para la ficha completa, `operaciones/habilidades.py`.

### Las diez de dominio

| ID | Regla que la define | Incertidumbre declarada (la más importante) |
|---|---|---|
| **H-01** | La huella es `abierto_sin_resolucion`: **la magnitud no entra**, porque avanza sola | *Un caso puede haber sido atendido por un canal que el CRM no registra: la ausencia de cierre NO prueba ausencia de atención* |
| **H-02** | Única señal de **nivel 0**; no es un comodín: exige objeto y campo nombrables | *Un campo vacío puede ser un dato que todavía no corresponde cargar* |
| **H-03** | `programada_para IS NULL` **no** implica sin programar | *La ausencia de plan no distingue "nadie la planificó" de "se planificó y no se registró"* |
| **H-04** | Un plan de semana futura en borrador **no** es señal | *Un plan puede estar acordado verbalmente y ejecutándose* |
| **H-05** | **BLOQUEADA por D-4** | *Sin definición de capacidad, cualquier umbral sería arbitrario* |
| **H-06** | Dice que venció; **no** dice que alguien incumplió | *Vencida no implica desatendida* |
| **H-07** | Declara una ausencia; **no** propone a quién asignar | *La ausencia del campo no prueba que nadie se esté ocupando* |
| **H-08** | Usa el motivo **registrado**, nunca uno deducido | *El motivo registrado puede estar desactualizado* |
| **H-09** | Ventana de 24 h | *La ventana es una convención, no una medición* |
| **H-10** | Nombra la actividad previa **concreta** | *Una cadena larga puede tener la causa varios pasos atrás* |

### Las cuatro transversales

| ID | Por qué no puede duplicarse |
|---|---|
| **H-C1** | Dos fórmulas serían dos colas |
| **H-C2** | Dos formatos harían la auditoría ilegible |
| **H-C3** | Dos criterios de huella romperían la deduplicación que M09-D cerró |
| **H-C4** | Duplicarla garantiza que una copia se relaje |

---

## 5. Versionamiento

**Esquema:** `<ID>@<entero>`. Nada más.

| Regla | Efecto |
|---|---|
| La versión sube cuando **cambia la condición** que la habilidad evalúa | no sube en cada despliegue: una versión que se mueve sola entrena a ignorarla |
| Una propuesta guarda la referencia **del momento** | una propuesta de hace seis meses sigue diciendo con qué definición se emitió |
| Cambiar la versión produce **otra huella** y no toca la ficha anterior | verificado por prueba |

Hoy las 14 están en **v1**, con fecha efectiva **2026-09-17**.

---

## 6. Registro literal congelado

**[MEDIDO]** Huellas sha256 sobre la serialización canónica (campos ordenados,
separadores fijos, UTF-8). Reproducibles: dos cálculos dan lo mismo.

```
H-01  c687c991fea79985b3dadaf78b751c4c31abe2335d30de08998c2259f37eda27
H-02  35dde6c3144bfac8f7931cf365beea0226a8b18739b866fde9bb74f346248add
H-03  6c4015d1921b6e316864fd5f3de95414c3626aac1c91fa153ac02ce43b62c926
H-04  6b9162f081dbcabece704938ba07f1f49fb16007fc11bebdd630f64e3b75f6ef
H-05  f1cf879ab7d5598a3bc8f9f188415a140dbba484cdbc912fac722a7cc9edc94c
H-06  95bf15dae3b34f46299f32a75fbce9169dd3ae7e5e2dd2f5981417703d244707
H-07  b1259873feeaf812a10ef0be7c794e9a6a825db56e2b704cf9ffd877fce203cb
H-08  fecce1b803d85afb36113cba3b213f238a620fccc760135b6de9a6579d979afd
H-09  39f2d79fb1cc77196407d8e2ede11e74bbf61ea2a2bcf47b6aa0bedb1387a841
H-10  c989375568a63b122116dd4125ac9701c613c451a08d963e1f68232a7b6eb456
H-C1  e11a07fd2e9a68ba726f97898ffd08a61b2c48ae223ec6385f7d1e69bc6dee6b
H-C2  1285c6ba7c92fcbe50c8dc65cb847ce29c7d862ec56855b3c5c609d6979ea340
H-C3  77881a05bd4bfad9e172cef13fdf5ad7c71fd92c34da92e56c4023f0e40c3472
H-C4  625f2faf089791ab8e1c40f48f2d43012416f1ffd7463f8badbda9f95634aea5
```

**Las 14 son distintas** — verificado por prueba. Ningún secreto entra en la
serialización: las fichas solo contienen descripciones.

**Cómo está congelado:** `MappingProxyType` sobre un diccionario literal, y
`@dataclass(frozen=True)` con tuplas. Agregar, quitar o editar levanta
`TypeError`. Sin `importlib`, sin registro dinámico, sin nombre que venga de
afuera — el mismo patrón que `nucleo/programador/registro.py`, y por el mismo
motivo: *el catálogo lo edita un operador; el código lo revisa alguien*.

---

## 7. Conocimiento

**[MEDIDO]** **11 de las 14 no tienen documento de conocimiento**, y la ficha lo
declara con una tupla vacía **en vez de inventar una referencia**.

| Ficha | Conocimiento |
|---|---|
| H-08 | `NovedadOperativa.TIPOS` — **existe**, verificado contra el modelo en una prueba |
| H-05 | `PENDIENTE — D-4: definición de capacidad operativa` |
| H-C4 | `PENDIENTE — D-3: guía de redacción sin atribución de culpa` |
| Las otras 11 | **vacío** — no hay documento |

**[PENDIENTE]** Los cinco documentos de M09-J FASE 7 siguen sin escribirse. No se
escribieron aquí: crearlos es D-3 y está fuera de alcance.

---

## 8. Procedimientos

Cada ficha vigente declara su procedimiento como una secuencia numerada — el que
el detector **ya ejecuta**. H-05 no declara procedimiento: documentar uno que
dependería de una definición inexistente sería inventarlo.

Ejemplo, H-03, que es el que más se corrigió:

```
1. Leer el estado operativo de la orden.
2. Si ya está en campo, completada, cancelada o en corrección: NO hay señal.
3. Buscar una ProgramacionOrden en planificada o confirmada.
4. Si existe: NO hay señal.
5. Si no existe: emitir señal citando el estado y la ausencia.
```

---

## 9. Evidencia

Cada ficha declara qué evidencia necesita, **clasificada por tipo**:

| Tipo | Fichas que lo usan | Ejemplo |
|---|---|---|
| **observado** | H-01, H-03, H-04, H-06, H-09, H-10 | `estado actual del caso` |
| **calculado** | H-01, H-C1 | `componentes de la prioridad` |
| **faltante** | H-02, H-03, H-04, H-07 | `ausencia de programación vigente, declarada como ausencia` |
| **humana** | H-08 | `el motivo de bloqueo tal como lo registró una persona` |

**La distinción que más importa** está en las fichas de H-02, H-03, H-04 y H-07:
un dato faltante se declara **como ausencia**, nunca como causa. *"No hay
registro de cierre"* no es *"nadie lo atendió"*.

---

## 10. Incertidumbre

**Las 14 declaran su incertidumbre** — es la sexta pregunta que M09-J encontró
sin responder, y ahora tiene lugar en cada ficha.

No es un sistema probabilístico y **no hay ningún porcentaje de confianza**: son
frases concretas sobre qué puede estar mal en el propio resultado. Ejemplos:

> **H-01:** *Un caso puede haber sido atendido por un canal que el CRM no
> registra: la ausencia de cierre NO prueba ausencia de atención.*

> **H-C4:** *La lista de 13 patrones prohibidos es una guarda, no una garantía:
> se puede atribuir culpa sin usar ninguna de esas palabras.*

> **H-05:** *Con 0 filas de disponibilidad, la ausencia de señal no significa
> ausencia de riesgo.*

---

## 11. Escalamiento

**Todas las de dominio escalan al Supervisor siempre**: una habilidad no emite
propuestas por su cuenta. Dos declaran además escalamiento a humano:

| Ficha | A humano cuando |
|---|---|
| H-03 | la orden ya está en campo sin ningún plan registrado |
| H-08 | el bloqueo persiste más de un ciclo sin novedad |

Las transversales no escalan: no emiten señales.

---

## 12. Nivel de autonomía

| Nivel | Fichas |
|:--:|---|
| **0 · observar** | H-02 y las 4 transversales |
| **1 · recomendar** | las otras 9 de dominio |
| 2, 3, 4 | **ninguna** |

**Ninguna declara herramienta de escritura.** Verificado por prueba sobre las 14.

Una ficha **no concede permisos**: documenta qué datos se consultan. La
autorización sigue viviendo donde vivía — la frontera externa y el interruptor —
y este paso no los tocó.

---

## 13. Relación con los detectores

**Detector ≠ habilidad.** La ficha **describe**; el detector **ejecuta**. No se
movió lógica y no se refactorizó `supervisor.py`.

El enganche son dos mapas derivados del registro:

```
POR_DETECTOR   10 entradas   _casos_abiertos_antiguos -> H-01, ...
POR_SENAL      10 entradas   caso_abierto_antiguo     -> H-01, ...
```

Y cuatro pruebas verifican que la ficha **no mienta** sobre el código:

1. cada detector nombrado **existe** en `supervisor.py` y es invocable;
2. cada señal nombrada **está declarada** en `PropuestaSupervisor.TIPOS_SENAL`;
3. **las 10 señales del modelo tienen ficha** — ninguna queda sin explicación;
4. cada detector aparece en el código real de `detectar()`, leído con `inspect`.

Si alguien renombra un detector, la prueba 1 falla. **Y lo correcto entonces es
corregir la ficha, no el código**: el código es la fuente canónica.

---

## 14. Relación con `PropuestaSupervisor`

**No se crearon campos ni migraciones.** `conocimiento_version` ya existía —
`CharField(128)`, vacío en las 52 propuestas de M09-E — y ahora se puebla.

**Un solo cambio funcional, de una línea**, en `registrar_propuesta`:

```python
conocimiento_version=habilidades.referencia_de(senal.tipo),
```

### Qué representa ese valor, exactamente

Guarda **solo la versión de la habilidad**, con el prefijo `habilidad:` puesto a
propósito:

```
conocimiento_version = "habilidad:H-01@1"
```

El campo se llama `conocimiento_version` y **hoy no existe ningún documento de
conocimiento versionado**. Poner ahí algo que pareciera una versión de
conocimiento sería inventar una precisión que no tenemos. El prefijo lo deja
explícito para quien lea la fila dentro de un año.

**[DISEÑO]** Cuando existan los documentos (D-3), el valor podrá extenderse a
`"habilidad:H-01@1 conocimiento:umbral-caso-antiguo@1"` **sin que ninguna fila
vieja cambie de significado**.

Una señal sin ficha devuelve `""` — el mismo valor que tenía antes. **Preferible
un campo vacío a una referencia inventada.**

### Lo que ahora se puede responder

```
propuesta.conocimiento_version = "habilidad:H-03@1"
        ↓
HABILIDADES["H-03"]  →  procedimiento, evidencia, incertidumbre,
                        reglas, detector, huella
```

---

## 15. Pruebas

**144 nuevas**, en `operaciones/tests/test_m09k_habilidades.py`.

| # | Exigencia del encargo | Resultado |
|:--:|---|:--:|
| 1 | Las 14 están registradas | ✔ |
| 2 | Cada una con definición no vacía | ✔ (14 casos) |
| 3 | Cada una con versión | ✔ (14) |
| 4 | Cada una con evidencia definida | ✔ (14) |
| 5 | Cada una con incertidumbre definida | ✔ (14) |
| 6 | Ninguna con herramienta de escritura | ✔ (14) |
| 7 | Ninguna altera autonomía | ✔ (14) |
| 8 | La definición literal es determinista | ✔ |
| 9 | Una versión histórica permanece estable | ✔ |
| 10 | Una versión nueva no modifica el contenido histórico | ✔ |
| 11 | `conocimiento_version` no recibe valores inventados | ✔ |
| 12 | `PropuestaSupervisor` conserva trazabilidad | ✔ (10 señales) |

Más: el registro está congelado, una ficha no se puede editar, la ficha no miente
sobre el código (4 pruebas), H-05 está bloqueada y es la única.

**Compatibilidad:**

```
antes de tocar nada   operaciones/tests/   180 passed
después                                    324 passed   (180 + 144)
regresiones                                0
```

---

## 16. Gaps

Diferencias entre lo que sería deseable y lo que hay. **Ninguna se corrigió
silenciosamente.**

| # | Gap | Estado |
|---|---|---|
| **G-1** | **11 de 14 fichas sin documento de conocimiento** | declarado como tupla vacía. **D-3** |
| **G-2** | `conocimiento_version` guarda solo la versión de habilidad | el campo es uno solo; documentado en §14. Sin falsa precisión |
| **G-3** | **H-05 bloqueada**: el detector corre pero le falta la definición de capacidad | **D-4** |
| **G-4** | La versión se sube a mano | deliberado: que suba sola la volvería ruido |
| **G-5** | La ficha describe el detector pero no lo genera | consecuencia de D-1: el código es canónico |
| **G-6** | `conocimiento_version` no se puebla retroactivamente | no se tocaron datos. Las 52 propuestas de la réplica siguen vacías, y producción tiene **0** propuestas |

---

## 17. Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R-1 | Que el código cambie y la ficha quede mintiendo | 4 pruebas de consistencia ficha↔código |
| R-2 | Que alguien lea `conocimiento_version` como versión de conocimiento | prefijo `habilidad:` + §14 + prueba que lo exige |
| R-3 | Que se suba la versión sin cambiar la condición, o al revés | **[RIESGO] no hay guarda automática**: es disciplina de revisión |
| R-4 | Que una ficha futura declare una herramienta de escritura | prueba sobre las 14 |
| R-5 | Que H-05 se dé por implementada porque tiene ficha | `estado=bloqueada` + 2 pruebas |
| R-6 | Que este documento y el código diverjan | el documento es una **vista**; las huellas permiten verificar |

---

## 18. Pendientes

| # | Qué | Dónde queda |
|---|---|---|
| **P-1** | Los 5 documentos de conocimiento | **D-3** |
| **P-2** | Definición de capacidad operativa → desbloquea H-05 | **D-4** |
| **P-3** | Quién aprueba un cambio de habilidad operativa | **D-2** |
| **P-4** | **Motor / trazabilidad de usos de habilidades**: los 63 usos tienen `conversation_id` NULL y `analista.py` hace `INNER JOIN` sobre esa columna, así que su tercera señal devuelve cero siempre | **fuera de M09-K por instrucción explícita.** No se tocó `motor.py`, `analista.py` ni `registrar_uso()` |
| **P-5** | B-7 (runtime fuera de `postgres`) | **no tocado** |
| **P-6** | M10 (RLS de `campo_*`) | **no tocado** |
