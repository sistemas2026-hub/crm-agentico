# Correcciones del usuario al diagnóstico del Supervisor

Abierto el 18/10/2026. El usuario corrige, caso por caso y numerados, cómo
diagnostica el Supervisor un ticket. Cuando termine de pasar casos:

1. las correcciones se convierten en reglas: en código lo que se pueda
   comprobar (SmartOLT, WispHub), y el resto en las instrucciones con las que
   el modelo lee el ticket;
2. se miden contra lecturas reales antes de encenderlas;
3. se vuelven a leer con ellas los pendientes que quedaron mal diagnosticados.

Los tickets se resumen sin datos del cliente: ni nombre, ni teléfono, ni
dirección.

---

## Corrección 1 · Fidelización con cambio de router y de plan

**El ticket**: internet intermitente / fidelización. Se autoriza cambio de
router por fidelización, cambio de plan a 100 Mb, el cliente tiene una C-Data
("CDTA") y se ve intermitencia en el servicio. Usuario antiguo.

| | Lo que diagnostiqué | La corrección |
|---|---|---|
| Grupo | trabajo pedido | ✓ |
| Labor | instalación, por la tabla grupo → labor | **correctivo**: es un cliente que ya existe y se lo retuvo. "Soporte" es correctivo; instalación es para clientes nuevos |
| Prioridad | alta, por fidelización | ✓ |
| Causa | el equipo viejo | el cliente pidió un plan más alto y su equipo no da esas megas por wifi |
| Medición | medir antes de salir | medir la ONU e informar lo que dé, **sin objetar el cambio**: ya está autorizado |
| Coordinación | aplicar el plan el mismo día y dejar una prueba de velocidad | ✓ |

**Reglas que salen de acá:**

1. **Un trabajo pedido sobre un cliente que ya existe es correctivo.**
   Instalación es solo para clientes nuevos. La tabla grupo → labor (hoy
   "trabajo pedido → instalación") tiene que distinguir cliente nuevo de
   cliente existente.
2. **La capacidad del equipo contra el plan**, comprobable en SmartOLT por el
   modelo de la ONU:
   - **C-Data**: wifi de una sola banda (2.4 GHz). No entrega por wifi las
     megas de un plan alto.
   - **C-Data CATV**: doble banda. Permite medir las megas completas por
     wifi, más fácil para el cliente y para el técnico.

   Si el plan pedido es alto y la ONU es una C-Data, el cambio de equipo está
   justificado.
3. **Una acción ya autorizada no se objeta.** Cuando el ticket trae el cambio
   autorizado (por fidelización, por cambio de plan), la medición informa pero
   no bloquea.

**Abierto**: desde cuántas megas un plan es "alto" para una C-Data de una
sola banda.

---

## Corrección 2 · Intermitencia con niveles altos

**El ticket**: "internet intermitente / niveles altos". En SmartOLT: en línea,
-28.24 dBm en la ONU y -29.59 dBm en la OLT, a 2 km. El historial de la señal
oscila: cerca de -23 dBm de 19:00 a 07:00, y entre -29 y -30 de día.

**Por qué el Supervisor lo dejaba para una persona**: la regla de hoy frena
una falla cuando la medición dice "en línea con la señal dentro del rango"
(-25 dBm o mejor). Si midió de noche, vio -23 dBm y concluyó que el reclamo y
la medición se contradecían. Y esa medición se guarda 24 horas.

**Diagnóstico correcto** (confirmado por el usuario): falla de servicio,
correctivo, pasa a Despacho. La causa probable es física: la oscilación de la
señal *es* la intermitencia (conector, curva en la acometida, empalme). Antes
de salir, mirar si otras ONU del mismo puerto cayeron a la misma hora: si
cayeron, es obra de red.

**Reglas que salen de acá:**

1. **Doble diagnóstico.** Antes de generar la propuesta, el Supervisor mide y
   compara con lo que reporta el ticket (la descripción, o la foto). Si la
   diferencia con el reporte original no es mucha, pasa a Despacho para que
   un técnico revise el servicio.
2. **En una intermitencia se mira el historial de la señal**, no solo el
   valor actual: si estuvo fuera de rango en las últimas 24 horas, la falla
   está confirmada.
3. **Cuando el técnico reporta el arreglo, el Supervisor vuelve a medir** para
   confirmar que la señal quedó en rango.

**Respuestas del usuario (18/10):**
- **"No mucha diferencia" es casi lo mismo.** Su ejemplo: el ticket reporta
  -23.01 / -23.38 dBm y el Supervisor mide -23.01 / -23.57 dBm (0.00 y 0.19 dB
  de diferencia). Vale con los niveles malos: si coinciden con el reporte y
  están fuera de rango, pasa. Propuesto como tolerancia: hasta 1 dB, a
  confirmar.
- **Si el Supervisor mide y los niveles están buenos, lo deja en revisión**
  para una persona. Leído junto con la regla 2: en revisión si el valor
  actual Y el historial de 24 horas están en rango; si el historial muestra
  caídas fuera de rango, la intermitencia está confirmada y pasa.
- **-25 dBm es el límite de la guía** que usa la empresa.

**Hoy no existe el doble diagnóstico**: la lectura interpreta el texto del
ticket y la medición va aparte; nada compara los niveles que reporta el
ticket con los que mide el Supervisor. Es lo que agrega la regla 1.

**Leer la foto pide un modelo con visión.** CLAUDE.md §5: un tercero nuevo
(visión) exige resolver la autorización de tratamiento antes de activarse.
Mientras tanto, el doble diagnóstico usa los niveles escritos en la
descripción.

---

## Caso 3 · Sin internet, LOS en rojo, "sin energía" descartada por el cliente

**Confirmado por el usuario sin correcciones** (18/10). Ya aplica las
correcciones 1 y 2.

**El ticket**: sin internet, no hace ping, LOS en rojo, no muestra niveles,
registra "sin energía". El cliente dice que todo está conectado y ya probó
otro tomacorriente. Foto del cliente: equipo encendido (PWR verde) con LOS en
rojo. SmartOLT: LOS desde hace 1 hora, sin lectura. El historial venía estable
entre -24 y -25 dBm hasta que cayó de golpe a LOS.

**Diagnóstico**: falla de servicio confirmada por pérdida de señal óptica;
correctivo; prioridad alta (cliente sin servicio); pasa a Despacho. Un corte
repentino y no una degradación apunta a la acometida o a un conector en la
caja. Antes de salir, mirar si otras ONU del mismo puerto cayeron a LOS a la
misma hora: si cayeron, es un corte de red.

**Por qué el Supervisor de hoy podría dejarlo pendiente**: si al medir el
equipo marcaba "sin energía", la regla actual lo frena ("es la casa del
cliente, hay que preguntarle si tiene luz"), y esa medición se guarda 24
horas.

**Regla:**

1. **La energía descartada por el ticket no frena.** Si la medición dice "sin
   energía" pero el ticket dice que el cliente ya probó otro tomacorriente, o
   que el equipo está encendido con LOS en rojo, la causa de energía queda
   descartada y pasa como falla de fibra.

---

## Caso 4 · Sin internet, LOS en rojo y "fibra partida" en la OLT

**Confirmado por el usuario sin correcciones** (18/10), incluida la regla
nueva.

**El ticket**: sin internet, no hace ping, LOS en rojo, no muestra niveles,
símbolo de fibra partida en la OLT, requiere visita técnica.

**Diagnóstico**: falla de fibra confirmada; correctivo; prioridad alta; pasa a
Despacho. Ya trae dos señales que coinciden: el LED de LOS en rojo que ve el
cliente y la fibra partida que se ve en la OLT. La ONU está encendida y no
recibe luz, así que no hay duda de energía. Con las reglas de hoy debería
pasar solo (caído por LOS es "falla confirmada"). Si queda pendiente, es por
otra cosa: todavía no se midió, la primera medición falló y espera una
segunda vuelta, o la lectura lo puso en otro grupo.

**Regla:**

1. **Varias ONU del mismo puerto en LOS a la vez es un corte de red.** Antes
   de despachar, mirar en SmartOLT si otras ONU del mismo puerto están en LOS
   desde la misma hora. Si hay varias, es una obra de red: un solo trabajo,
   no una visita por cliente.

---

## Dónde quedó cada regla (19/10/2026)

Construidas en `operaciones/` (Supervisor) y `campo/cuadrillas.py`. Las que
hacen pasar más casos van detrás de la tarea delegada
`pasar_a_despacho_con_las_correcciones` y, mientras no se delegue, solo se
cuentan en sombra. Detalle y decisiones en
`SPEC/objetivos/supervisor-aplica-las-correcciones.md`.

| Regla | Dónde | Cómo |
|---|---|---|
| 1.1 Trabajo pedido de un cliente que ya existe = correctivo | `cuadrillas.LABOR_POR_GRUPO_DE_FABRICA`, `armado_de_jornadas.demanda_de_despacho` | Tabla de fábrica: trabajo pedido → correctivo, `instalacion_nueva` → instalación. Cliente nuevo = el ticket cuelga del cliente de instalaciones del ISP; sin barrio, se suma a las zonas de las cuadrillas de instalación. Encendida (si la empresa no guardó su propia tabla) |
| 1.2 Capacidad de la C-Data contra el plan | — | **Pendiente (tanda 2)**: falta la banda de cada tipo de ONU como dato de la empresa |
| 1.3 Una acción ya autorizada no se objeta | `paso_a_despacho.decidir`, clave `accion_autorizada` de la lectura | Detrás de la tarea; en sombra hasta delegarla. Solo si el ticket lo escribió una cuenta con nombre de la empresa |
| 2.1 Doble diagnóstico | `paso_a_despacho.niveles_reportados` y `_doble_diagnostico` | Los niveles escritos en el ticket contra la medición, con 1 dB de tolerancia. Informa en el motivo; no decide. Encendido. La foto no (pide visión, §5) |
| 2.2 El historial de 24 h | `medicion_de_fallas` (hasta dos re-mediciones a 8 h, e historial), `paso_a_despacho._la_falla_en_el_historial` | Con las mediciones del propio Supervisor. La re-medición corre siempre, con tope (no es polling), y nunca reemplaza a la medición; decide la más reciente, y la serie, solo con la tarea |
| 2.3 Volver a medir después del arreglo | `verificacion_de_arreglos` (fase del ciclo) | Informa en la propuesta si la señal quedó en rango. Encendida. Hasta tres intentos por orden; no mide un cambio de equipo |
| 3.1 La energía descartada por el ticket no frena | `paso_a_despacho.decidir`, clave `energia_descartada` | Detrás de la tarea; en sombra hasta delegarla |
| 4.1 Varias ONU del mismo puerto en LOS = obra de red | — | **Pendiente (tanda 2)**: falta la medición en vivo de SmartOLT por puerto y decidir "un solo trabajo" |
| Releer los pendientes mal diagnosticados | `diagnostico_de_ticket.le_falta_la_version` | Las fallas que frenan con una lectura de antes se releen una vez con las claves nuevas (y con las instrucciones nuevas si la tarea está delegada). Si la relectura las lee como trabajo u obra, eso también espera a la tarea |
