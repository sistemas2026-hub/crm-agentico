# M03-E1 — Auditoría y diseño de secuenciación operativa

**Fecha:** 2026-09-18
**Alcance:** auditoría y diseño. **0 código, 0 migraciones, 0 modelos, 0 endpoints, producción solo `SELECT`.**

---

## RESUMEN EJECUTIVO

La auditoría encontró dos cosas que reformulan el problema que M03-E1 venía a
estudiar.

### 1. La duplicidad no es un borde: es el estado por defecto

**[MEDIDO]** `secuencia` es `smallint NOT NULL` con `default = 0` puesto por
Django. El serializador la declara **opcional**.

> **Si nadie la envía, todas las líneas del plan valen 0.** Un plan de diez
> órdenes creado sin tocar el campo tiene **diez secuencias idénticas**.
>
> La colisión que M03-D3.2 anticipó al arrastrar la secuencia **no la introduce
> el arrastre**: ya era la línea base. Arrastrarla, de hecho, es lo único que
> hoy puede producir un valor distinto de 0 en una línea nueva.

### 2. `secuencia` se puede escribir y **no se puede leer**

**[MEDIDO]** Inventario completo de sus consumidores:

| Superficie | ¿Aparece? |
|---|---|
| respuestas de la API (`programar`, `reprogramar`) | **NO** — devuelven `linea`, `dia`, `hora_inicio`, `estado` |
| cualquier endpoint de lectura de `ProgramacionOrden` | **NO EXISTE tal endpoint** |
| frontend | **0 coincidencias** |
| PRD, ARQUITECTURA, directivas, docs | **0 coincidencias** |
| M09 (`supervisor.py`) | **0 coincidencias** |

> **Hoy el campo es de solo escritura.** Se puede enviar por la API y **no hay
> forma de volver a verlo**, ni por API, ni por pantalla, ni por informe.

**[DISEÑO] Consecuencia para M03-E2:** cualquier regla de ordenamiento que se
implemente ahora sería **inobservable** — nadie podría comprobar su efecto sin
consultar la base a mano. **Eso condiciona el alcance de E2 más que la elección
entre A/B/C/D.**

### 3. Y una tranquilidad medida sobre M09

**[MEDIDO]** M09 **no lee `secuencia` ni una vez**. Su única exposición es
indirecta: `_programacion_vigente(...)` hace `.first()` heredando
`Meta.ordering`. Pero esa consulta filtra **por una sola orden**, y desde
M03-D3.2 la invariante I-1 impide que una orden tenga dos líneas vigentes.

> **Una secuencia duplicada entre órdenes distintas no puede afectar a M09**, y
> M09 no puede interpretarla como prioridad ni como garantía: **nunca la mira.**

---

## 1. Estado actual medido

**[MEDIDO]** Producción, solo `SELECT` (`read_only = True`):

```
operaciones_programacion_orden .... 0 filas
operaciones_programacion_semanal .. 0 filas
```

> **Ninguna línea de plan ha existido nunca en producción.** Todo lo que sigue
> sale de leer el modelo, los servicios y el esquema — no de observar datos.

---

## 2. Evidencia de modelo

**[MEDIDO]** `operaciones/models.py:443`:

```python
secuencia = models.PositiveSmallIntegerField(
    default=0,
    help_text="Orden dentro de la jornada. NO es una ruta optimizada: "
              "es el orden propuesto.")
```

**[MEDIDO]** Esquema real en producción:

| columna | tipo | nulo | CHECK |
|---|---|:--:|---|
| `dia` | `date` | **NO** | — |
| **`secuencia`** | `smallint` | **NO** | **`secuencia >= 0`** |
| `prioridad` | `smallint` | **NO** | `prioridad >= 0` |
| `zona` | `varchar` | **NO** | — |
| `estado` | `varchar` | **NO** | — |

**[MEDIDO]** Constraints e índices de la tabla:

```
UNIQUE  unique_orden_por_programacion  (programacion_id, orden_id)
CHECK   secuencia >= 0        CHECK  prioridad >= 0
índices  (org_id, dia) · orden_id · org_id · programacion_id · updated_by_id · pk
```

> **No hay ninguna constraint ni índice que involucre `secuencia`.** La base
> admite duplicados sin objetar, y **no existe índice `(dia, secuencia)`**.

**[MEDIDO]** `Meta.ordering = ["dia", "secuencia"]` — **dos claves, sin tercera**.

---

## 3. Evidencia de servicios

| Servicio | Qué hace con `secuencia` |
|---|---|
| **`programar_orden`** | la acepta **opcional**; si llega `None` **no la pasa** y vale el default del modelo (`0`) |
| **`reprogramar_orden` · caso A** (mismo plan) | **no la toca**: `update_fields=["dia","hora_inicio","updated_by","updated_at"]` — la línea conserva la que tenía |
| **`reprogramar_orden` · caso B** (otro plan) | **la arrastra** desde la línea anterior, junto con `zona` y `prioridad` *(corregido en M03-D3.2)* |
| **`registrar_contingencia`** | **no toca ninguna línea** |
| **`publicar_programacion`** | **no la lee, no la valida, no la modifica** |
| **`revisar_coherencia`** | **no la comprueba**; solo la usa como criterio de orden en `_lineas_vigentes` |

**[MEDIDO]** Vía de entrada, `campo/serializers.py:238`:

```python
secuencia = serializers.IntegerField(required=False, min_value=0,
                                     max_value=32767, allow_null=True,
                                     default=None)
```

**[MEDIDO]** El servicio traduce `None` a *"no la mandes"*:

```python
**({"secuencia": secuencia} if secuencia is not None else {}),
```

> Es decir: **`null` y "campo ausente" producen lo mismo — el default 0.**

---

## 4. Evidencia de consumidores

**[MEDIDO]** Los **cuatro** usos, y los cuatro son *ordenar*:

| # | Dónde | Para qué |
|:--:|---|---|
| 1 | `Meta.ordering = ["dia","secuencia"]` | orden por defecto de cualquier consulta |
| 2 | `_lineas_vigentes(...).order_by("dia","secuencia")` | M03-C, al revisar coherencia |
| 3 | `_ordenes_con_dos_lineas_vigentes(...).order_by("dia","secuencia")` | M03-D3.2, para listar las líneas del mensaje |
| 4 | `supervisor._programacion_vigente(...).first()` | **hereda** el ordering; filtra por **una sola orden** |

**[MEDIDO]** **Ningún consumidor calcula nada con ella.** No hay agrupación, ni
suma, ni comparación, ni regla que dependa de su valor.

**[MEDIDO]** `__str__` la muestra (`f"{self.dia} #{self.secuencia} -> OT ..."`),
y eso solo se ve en el **admin de Django**.

---

## 5. Significado actual de `secuencia`

**[DECISIÓN APROBADA]** Representa el **ORDEN PROPUESTO**. No es ruta
optimizada, ni compromiso rígido, ni garantía de atención, ni incumplimiento, ni
prioridad por sí sola.

**[MEDIDO]** Y el propio modelo lo dice, desde antes de que existiera M03-D:
*"Orden dentro de la jornada. NO es una ruta optimizada: es el orden propuesto."*

### Las siete definiciones que el encargo pide, con lo que hoy las sostiene

| Concepto | Qué significa **hoy**, medido |
|---|---|
| **orden propuesto** | una sugerencia de en qué orden atender el día. **Nada la hace cumplir y nadie la lee** |
| **posición** | el valor de `secuencia` dentro de un `dia`. No es un índice: **no hay unicidad, ni continuidad, ni rango declarado** más allá de `0..32767` |
| **desempate** | **NO EXISTE.** `ordering` tiene dos claves y ninguna tercera: dos líneas con el mismo `dia` y la misma `secuencia` salen en **orden no determinista** |
| **ausencia de secuencia** | **no es representable.** La columna es `NOT NULL`; "no la envié" y "la envié en null" producen **`0`** |
| **duplicidad** | **permitida por la base** y **producida por defecto**: sin valor explícito, todas las líneas valen `0` |
| **cambio de día** | caso A: la línea se actualiza y **conserva** su secuencia. Caso B: la línea nueva la **arrastra** |
| **cambio de plan** | es el caso B. La línea vieja pasa a `reprogramada` **conservando su secuencia**, y la nueva la copia |

---

## 6. El problema de la duplicidad

### Lo que el encargo describía

```
Día X:  secuencia 1 · secuencia 2
Mover otra OT al mismo día con secuencia 1:
        secuencia 1 · secuencia 1 · secuencia 2
```

### Lo que la medición añade

**[MEDIDO]** El caso **más frecuente** no es ése, sino éste:

```
Día X:  secuencia 0 · secuencia 0 · secuencia 0 · secuencia 0
```

> Porque `secuencia` es opcional y su default es `0`. **Un plan cargado sin
> enviar el campo tiene todas sus líneas empatadas.**

### Qué pasa hoy con un empate

**[MEDIDO]** `ORDER BY dia, secuencia` **sin tercera clave**.
**[DISEÑO]** En SQL, las filas que empatan en todas las claves de orden salen en
el orden que el plan de ejecución produzca. **No es estable ni reproducible**, y
puede cambiar entre dos consultas idénticas.

**[RIESGO]** Hoy eso **no tiene consecuencia observable** —nadie lista un día—
pero la tendría en el momento en que exista una pantalla de jornada.

### Las tres duplicidades, que no son la misma cosa

| | Tipo | Cómo se produce | ¿Es un defecto? |
|---|---|---|---|
| **A** | **técnicamente válida** | dos órdenes del día a las que nadie asignó orden: ambas en `0` | **no** — es el default |
| **B** | **accidental** | una reprogramación arrastra `secuencia=3` a un día que ya tiene un `3` | **[PENDIENTE]** — depende de la decisión |
| **C** | **ausencia de secuencia** | **no existe**: la columna es `NOT NULL` | **no aplica** |

> **[MEDIDO] El tipo C no es representable.** No hace falta decidir nada sobre
> él: la base no admite el estado.

---

## 7. Matriz de escenarios

**[MEDIDO]** Los catorce, con el comportamiento actual — **sin proponer cambios**.

| # | Escenario | Comportamiento hoy | Observación |
|:--:|---|---|---|
| **1** | 2 OT mismo día, secuencias distintas | orden determinista por `dia, secuencia` | **nadie lo lee**: no hay endpoint de jornada |
| **2** | 2 OT mismo día, **misma secuencia** | permitido; **empate sin desempate** → orden no determinista | **es el caso por defecto** |
| **3** | reprogramar a otro día **conservando** secuencia | caso A conserva, caso B arrastra *(D3.2)* | puede coincidir con lo que ya hay ese día |
| **4** | reprogramar **dos** OT al mismo día | cada una conserva la suya | si coinciden → escenario 2 |
| **5** | agregar OT a plan **publicado** | `programar_orden` exige causa; `secuencia` = lo enviado o **0** | **la adición formal no dice nada de la secuencia** |
| **6** | reprogramar **dentro del mismo plan** | la línea se **actualiza**; `secuencia` **no está en `update_fields`** → intacta | |
| **7** | reprogramar **hacia otro plan** | línea vieja → `reprogramada` **conservando** su secuencia; la nueva la copia | quedan **dos filas con el mismo número**, una histórica |
| **8** | plan **borrador** | **sin diferencia** para `secuencia` | |
| **9** | plan **publicado** | **sin diferencia**: `publicar_programacion` no la lee ni la valida | |
| **10** | secuencia **NULL** | **IMPOSIBLE** — columna `NOT NULL`; `null` en la API se traduce a "no enviar" → `0` | |
| **11** | secuencia **0** | **el default**. Todas las líneas sin valor explícito lo comparten | |
| **12** | secuencia **negativa** | **IMPOSIBLE** — `CHECK (secuencia >= 0)` en base **y** `min_value=0` en el serializador | dos capas |
| **13** | misma secuencia, **misma zona** | idéntico al escenario 2 | **`zona` no participa en el orden** |
| **14** | misma secuencia, **zonas distintas** | idéntico al escenario 2 | **`zona` no participa en el orden** |

---

## 8. Zona y prioridad

**[MEDIDO]** **Ninguna de las dos participa en el ordenamiento.**

```python
Meta.ordering = ["dia", "secuencia"]      # zona y prioridad NO están
```

| Campo | Semántica declarada | ¿Algún consumidor la aplica? |
|---|---|:--:|
| **`zona`** | *"Zona que cubre en esa franja. Vacío = cualquiera"* (en `DisponibilidadTecnico`); en la línea es texto libre sin catálogo | **NO** |
| **`prioridad`** | **`"Menor corre antes. 0 = lo más urgente."`** | **NO** |

> **[RIESGO] `prioridad` está en la misma situación que `secuencia`, y es más
> llamativo:** tiene una regla de negocio **escrita en el `help_text`** —*"menor
> corre antes"*— y **ningún código la aplica**. No aparece en ningún `order_by`,
> ni en ninguna comparación.
>
> Se documenta porque el encargo pide no asumir que participan solo por estar en
> la tabla. **No participan.**

**[MEDIDO]** Lo único que hacen los tres campos hoy es **viajar juntos** al
reprogramar entre planes (M03-D3.2).

---

## 9. Plan borrador y plan publicado

**[MEDIDO]** `publicar_programacion` **no menciona `secuencia`**: no la lee, no
la valida, no la congela, no la reordena. Publicar cambia `estado`,
`publicada_en`, `publicada_por` y `updated_by`, y nada más.

**[MEDIDO]** `revisar_coherencia` —la puerta que publicar atraviesa— comprueba
organización, semana, coherencia día↔`programada_para` e I-1. **No comprueba
`secuencia`.**

### Las cuatro alternativas del encargo

| | Alternativa | Qué exigiría | Evidencia a favor hoy |
|---|---|---|---|
| **P1** | publicar **congela** las secuencias | una regla nueva y una vía para cambiarlas después | **ninguna** |
| **P2** | publicar **permite** cambios | nada — es lo que pasa | es el comportamiento actual |
| **P3** | publicar **exige** reordenamiento | un algoritmo, y decidir qué es "bien ordenado" | **ninguna** |
| **P4** | publicar **simplemente publica el orden propuesto existente** | nada | es el comportamiento actual, dicho de otra forma |

**[DISEÑO]** **P2 y P4 describen la misma conducta.** La diferencia entre ellas
es de intención declarada, no de código.

**[PENDIENTE]** Ninguna evidencia sostiene P1 ni P3. **No se elige.**

---

## 10. Reprogramación

**[MEDIDO]** Qué hace hoy cada ruta con `secuencia`:

| Transición | Qué pasa | Dónde |
|---|---|---|
| **cambia de día, mismo plan** | **conserva** — la línea se actualiza y `secuencia` no está en `update_fields` | `reprogramar_orden` caso A |
| **cambia de semana / de plan** | **arrastra** — la línea nueva copia la de la anterior | caso B *(M03-D3.2)* |
| **vuelve por corrección** | idéntico a normal: caso A conserva, caso B arrastra | `RUTA_CORRECCION` |
| **entra por contingencia** | **no se toca ninguna línea** | `registrar_contingencia` |

**[DECISIÓN APROBADA]** Este comportamiento **no se modifica en M03-E1**.

**[RIESGO]** El arrastre puede llevar un número a un día que ya lo tiene
(duplicidad tipo **B**). **Lo que M03-E tiene que decidir es qué significa eso**,
no si ocurre.

---

## 11. `revisar_coherencia`

**[MEDIDO]** Hoy detecta cuatro cosas, **ninguna sobre `secuencia`**:
organización de la línea, organización de la orden, día dentro de la semana,
coherencia con `programada_para`, más **I-1** (dos líneas vigentes).

### Las tres alternativas para la duplicidad

| | Tratamiento | A favor | En contra |
|---|---|---|---|
| **ERROR** | bloquea la publicación | fuerza a resolverla antes de comprometer el plan | **bloquearía el caso por defecto**: un plan donde nadie envió secuencias tiene todo en `0` y **no se podría publicar nunca** |
| **WARNING** | informa y deja publicar | no rompe nada | `revisar_coherencia` devuelve hoy **una lista de bloqueos**, no de avisos: habría que darle dos semánticas |
| **INFORMACIÓN** | no participa en publicar | coherente con "orden propuesto" | quien mira el plan no se entera |

**[RIESGO] El argumento decisivo, medido:** tratar la duplicidad como ERROR
**bloquearía la conducta por defecto del sistema**. Con `secuencia` opcional y
default `0`, el plan típico —el que nadie secuenció— es exactamente el que
tendría más duplicados.

> Eso **no elige la opción**: dice que ERROR solo sería viable junto con una
> decisión adicional sobre el default, y esa decisión no está en el encargo.

**[PENDIENTE]** No se decide.

---

## 12. M09

**[MEDIDO]** `supervisor.py` menciona `secuencia` **0 veces**.

**[MEDIDO]** Su única exposición es indirecta:

```python
def _programacion_vigente(org, orden):
    return (ProgramacionOrden.objects
            .filter(org=org, orden=orden, estado__in=(PLANIFICADA, CONFIRMADA))
            .select_related("programacion")
            .first())          # <- hereda Meta.ordering = ["dia","secuencia"]
```

**[DISEÑO]** Dos hechos acotan el riesgo:

1. La consulta filtra **por una sola orden**, así que nunca compara líneas de
   órdenes distintas: **una duplicidad entre órdenes no la afecta**.
2. Desde M03-D3.2, **I-1 impide que una orden tenga dos líneas vigentes**, así
   que `.first()` normalmente elige entre **una sola**.

**[MEDIDO]** Cómo interpreta M09 los tres conceptos:

| | Interpretación de M09 |
|---|---|
| **`dia`** | lo usa como **evidencia textual** (*"hay plan vigente para el {linea.dia}"*) y en `datos.dia_planificado`. **No lo compara** con `programada_para`: eso lo hace `revisar_coherencia` |
| **`secuencia`** | **no la usa** |
| **programación vigente** | `estado in (planificada, confirmada)` — la misma definición que M03-C y M03-D |

> **Confirmado lo que el encargo pedía verificar: una secuencia duplicada NO
> puede ser interpretada por M09 como prioridad ni como garantía, porque M09
> nunca lee el campo.**

**[MEDIDO]** Lo que M09 sí tiene es su **propia** noción de prioridad
(`_prioridad()`, `PropuestaSupervisor.prioridad`), **independiente** de
`ProgramacionOrden.prioridad`. Comparten el criterio *"menor es más urgente"* y
son campos distintos en tablas distintas.

**No se modificó M09.**

---

## 13. Decisiones empresariales necesarias

| # | Decisión | Sección | Bloquea |
|:--:|---|:--:|---|
| **E-1** | **¿Qué hacer ante una duplicidad?** A permitir · B recompactar · C reasignar al cambiar de día · D otra | §6, §7 | **M03-E2** |
| **E-2** | **¿Qué significa `secuencia = 0` por defecto?** ¿"sin ordenar" o "el primero"? Hoy es ambas cosas a la vez | §6 | **M03-E2** |
| **E-3** | **¿La secuencia debe ser visible?** Hoy es de **solo escritura**: no hay forma de leerla | §RESUMEN | **M03-E2** |
| **E-4** | **¿Publicar hace algo con las secuencias?** P1/P2/P3/P4 | §9 | M03-E2 |
| **E-5** | **¿Duplicidad en `revisar_coherencia`: ERROR, WARNING o nada?** | §11 | M03-E2 |
| **E-6** | **¿`prioridad` debe participar en el orden?** Tiene regla escrita y ningún consumidor | §8 | M03-E3 |
| **E-7** | **¿`zona` debe agrupar la jornada?** Hoy es texto libre sin catálogo | §8 | M03-F |

**[PENDIENTE] Ninguna se toma aquí.**

> **E-2 y E-3 no estaban en el encargo y son las que más pesan.** E-1 no se puede
> responder bien sin saber qué significa el `0` por defecto, ni si alguien va a
> ver el resultado.

---

## 14. Recomendación de diseño

**No se elige entre A, B, C y D** (§REGLA ABSOLUTA). Lo que sigue es lo que la
medición permite afirmar **sea cual sea la opción**.

### 14.1 Lo que es invariante a las cuatro opciones

**[DISEÑO]**

1. **Hace falta un desempate determinista.** Con `ordering` de dos claves, dos
   líneas empatadas salen en orden arbitrario **en cualquiera de las cuatro
   opciones** — incluso en la A, que acepta duplicados. Una tercera clave
   estable (`hora_inicio`, `created_at` o `id`) hace el orden reproducible **sin
   decidir nada sobre la duplicidad**.
2. **`secuencia` necesita una vía de lectura.** Sin ella, ninguna regla es
   observable ni comprobable de extremo a extremo.
3. **Nada de esto exige migración.** Cambiar `Meta.ordering` **sí** genera una
   migración de estado en Django; añadir una tercera clave en los `order_by`
   explícitos, **no**. Es una diferencia que M03-E2 debe medir antes de elegir
   dónde tocar.

### 14.2 Lo que cada opción costaría

| | Opción | Coste medido |
|---|---|---|
| **A** | permitir duplicados | **cero código**; exige el desempate de 14.1 para que el orden sea reproducible |
| **B** | recompactar automáticamente | hay que definir **cuándo** (¿al programar? ¿al publicar?) y **sobre qué conjunto** (¿el día? ¿el día por zona?). Reescribe líneas que nadie pidió mover — incluidas las de **planes publicados** |
| **C** | reasignar al cambiar de día | **revierte la corrección de M03-D3.2**: volvería a hacer que el caso A y el caso B se comporten distinto, salvo que también se reasigne en A |
| **D** | otra | — |

**[RIESGO]** **La opción C choca con una decisión ya aprobada.** M03-D3.2 igualó
los dos casos precisamente para quitar esa asimetría; elegir C exigiría decidir
además qué hace el caso A.

### 14.3 El orden en que conviene decidir

**[DISEÑO]**

```
E-3 (¿se lee?)  →  E-2 (¿qué es el 0?)  →  E-1 (¿qué hacer con el duplicado?)
                                             →  E-4 y E-5 (publicar y coherencia)
```

> **No es una preferencia: es dependencia.** Decidir qué hacer con un duplicado
> antes de saber si alguien lo va a ver, y qué significa el valor que la mitad de
> las líneas va a tener por defecto, es decidir sobre algo que todavía no está
> definido.

---

## 15. Alcance de M03-E2

**[DISEÑO]** Lo que M03-E2 puede hacer **sin ninguna decisión nueva**:

| | Trabajo | Por qué no necesita decisión |
|---|---|---|
| **1** | **Vía de lectura de la jornada**: un endpoint que liste las líneas vigentes de un día/plan, con `secuencia`, `zona` y `prioridad` | no cambia ninguna regla; hace observable lo que ya existe. Habilita E-3 |
| **2** | **Desempate determinista** en los `order_by` explícitos | el orden deja de ser arbitrario **sin** decidir nada sobre duplicados |
| **3** | **Medir** cuántas líneas quedan empatadas en escenarios reales | da a E-1 y E-2 el dato que hoy no existe (0 filas en producción) |

**Fuera de alcance hasta que se decida:**

```
recompactación ............ E-1
reasignación al mover ..... E-1  (y choca con M03-D3.2)
validación en publicar .... E-4, E-5
prioridad en el orden ..... E-6
agrupación por zona ....... E-7
rutas, distancia, tiempos de desplazamiento, clustering, optimización ... fuera de M03-E
```

**[DEPENDENCIA]** Qué necesita cada fase posterior:

| Fase | Necesita |
|---|---|
| **M03-E2** | E-3 para ser útil; **nada** para empezar por la vía de lectura |
| **M03-E3** | E-1, E-2, E-4, E-5 |
| **M03-F** (cuadrillas) | E-7, y la decisión D-1 de M03-A sobre si la cuadrilla es entidad estable |
| **M03-G** (capacidad) | **nada de secuencia** — depende de duración y jornada, que siguen sin existir |

**[RIESGO] Y el recordatorio que no ha cambiado:** **0 planes y 0 líneas en
producción**, y las 3 órdenes reales clasifican como **contingencia**. M03-E
trabaja sobre estructuras que todavía no tienen una sola fila.

---

```
código ......... 0     modelos ....... 0     migraciones ... 0
endpoints ...... 0     M09 ........... sin tocar     decisiones tomadas ... 0
producción ..... SIN CAMBIOS (solo SELECT, read_only = True)
commit ......... no
```
