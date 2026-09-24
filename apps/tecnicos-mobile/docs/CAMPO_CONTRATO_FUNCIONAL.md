# Dexter Campo — qué muestra, qué permite, qué prueba

Auditoría de las tres dimensiones que definen la aplicación de un técnico:
**el dato que ve**, **la acción que puede tomar** y **la evidencia que deja**.

Esto no es el contrato de versión candidata
([`CAMPO_RELEASE_CONTRACT.md`](CAMPO_RELEASE_CONTRACT.md)), que dice qué está
terminado y no se puede romper. Esto dice qué **debería** haber y hoy no está,
con la clase de cada hueco — porque no todos se arreglan igual:

| | Clase | Cómo se resuelve |
|---|---|---|
| **A** | Defecto real | Se arregla en código. Hay una expectativa razonable que el sistema no cumple |
| **B** | El dato no existe | No hay nada que dibujar. Se resuelve construyendo la fuente, no la pantalla |
| **C** | Decisión de producto | Alguien tiene que decidir qué se quiere. Escribir código antes es adivinar |

Medido el 24/09/2026 contra `feat/campo-diseno-stitch`, leyendo el backend
(`django-crm/backend/campo/`) y las ocho pantallas de la aplicación.

---

## 1 · Lo que muestra

El backend expone bastante más de lo que uno esperaría, y casi todo llega a la
pantalla: cliente, acceso, plan, ticket de origen, franja prometida, requisitos
de seguridad, devolución del supervisor con su observación. Buscando huecos de
*datos* aparecieron pocos.

El hueco real es otro y es más incómodo: **el vocabulario de tipos del
formulario no coincide entre las dos puntas.**

### 1.1 · `entero` no existe para la aplicación · **A**

El backend declara ocho tipos (`campo/services/validador.py`):

```
texto · entero · decimal · booleano · seleccion · fecha · foto · documento
```

La aplicación decide el teclado así
(`widgets/formulario_de_campo.dart`):

```dart
final bool esNumero = tipo == 'numero' || tipo == 'decimal' || tipo == 'integer';
```

`numero` e `integer` **no los emite el backend nunca**. `decimal` coincide por
casualidad — es el único de los tres que existe del otro lado. Así que un
campo declarado `entero` abre un teclado de texto, y alguien con guantes tiene
que buscar los números.

### 1.2 · `fecha` es un campo de texto libre · **A**

Cae en el `default` del `switch`. Se puede escribir "el martes" y el formulario
lo acepta; el rechazo llega después, del validador del servidor, cuando la
persona ya se fue de la casa del cliente.

### 1.3 · `foto` y `documento` como tipo de **campo** piden escribir · **A**

También caen en `default`. Son tipos válidos del esquema —distintos de las
evidencias, que van por su propia lista— y hoy producen una caja de texto donde
se esperaba una cámara.

### 1.4 · Dos de ocho · **A**

La aplicación dibuja de verdad `seleccion` y `booleano`. Los otros seis son el
mismo `TextField`. El esquema puede pedir ocho cosas distintas y la pantalla
sabe hacer dos.

**Las cuatro son el mismo arreglo**, y cae dentro del invariante que ya existe
—un solo lugar lee el esquema, `campo_del_formulario.dart`— así que es el
cambio más seguro de todos los de este documento.

### 1.5 · Sólo hay dos tipos de trabajo · **B**

`seed_campo_demo` siembra `ftth_instalacion` y `ftth_correctivo`. El catálogo
real de un ISP tiene bastante más: retiro, traslado, cambio de plan, revisión
de red, visita fallida, mantenimiento preventivo.

No es un hueco de la aplicación: la aplicación dibuja lo que la plantilla
diga. Es la conversación de producto más grande de este documento, y la que
más depende de la empresa — o sea que es configuración por tenant
(CLAUDE.md §3.3), no código.

---

## 2 · Lo que permite hacer

La máquina de estados está completa y bien cableada:

```
asignada ──► en camino ──► en sitio ──► completada ──► cerrada
                                            │
                                            ▼
                                  corrección requerida ──► volver al sitio
```

El camino de vuelta funciona, y desde el 22/09/2026 la devolución llega al
teléfono con **qué** requisitos rehacer y la observación del supervisor. Antes
eso se averiguaba por teléfono.

### 2.1 · No existe "llegué y no se pudo" · **C → A**

El hallazgo más importante de esta auditoría, y el que menos se parece a un
bug.

`cancelar` existe en el backend y la aplicación **no lo ofrece**. Está
documentado, y la razón es buena (`detalle_orden/pasos_orden.dart`):

> *cancelar un trabajo es una decisión de operaciones, no del técnico parado
> en la puerta.*

De acuerdo. Pero entonces falta la otra mitad, y no está en ningún lado: **el
técnico que llega y no puede trabajar no tiene ninguna salida.**

- No hay nadie en la casa.
- La dirección está mal.
- El poste es de otra empresa y no hay permiso.
- El cliente no deja entrar.
- Llueve y no se sube a la escalera.

Hoy esa orden se queda en `en_sitio` hasta que alguien llame por teléfono. Las
dos salidas que la pantalla ofrece son *completar* —que sería mentir— y nada.

Esto **no es cancelar** (eso lo decide la oficina, con razón) ni completar (no
se hizo el trabajo). Es un tercer desenlace que el sistema no tiene, y es el
caso más frecuente que existe después del trabajo normal.

Se llama **C** porque antes del código hay que decidir:

- ¿Es un estado nuevo del backend, o un `completada_campo` con un resultado
  "no realizado"?
- ¿Cuenta como trabajo hecho de la jornada, o no?
- ¿Qué evidencia exige? (una foto de la puerta cerrada prueba bastante)
- ¿Quién lo resuelve después, y en qué pantalla lo ve?
- ¿Reagenda solo, o alguien lo reagenda?

Y pasa a **A** en cuanto se decida, porque arrastra migración, pantalla y
probablemente bandeja de supervisión.

---

## 3 · La evidencia que se toma

Lo que está bien, y conviene no romperlo:

- **Sólo cámara, nunca galería** (`ImageSource.camera`). Una evidencia no
  puede ser una foto vieja de otro trabajo.
- **Vuelta dirigida**: lo que el supervisor devolvió exige evidencia *de esta
  vuelta*; lo que no devolvió conserva la que tenía. Nadie repite ocho fotos
  porque una estaba mal.
- **La firma del cliente es una evidencia más**: se captura, se guarda, sube
  por la misma cola y se protege igual al cerrar sesión. Una empresa que no
  pida firma simplemente no la declara.

### 3.1 · Las fotos no dicen cuándo ni dónde se tomaron · **A**

El backend las espera. Están en el serializer, con su ayuda escrita:

```python
capturada_en_cliente = serializers.DateTimeField(required=False, allow_null=True)
metadatos_captura    = serializers.DictField(required=False, default=dict)
```

> *"Timestamp del reloj del dispositivo en el momento de la captura"*
> *"Metadatos técnicos: coordenadas GPS del móvil, precisión, modelo"*

**La aplicación no los manda nunca.** Se buscó en todo `lib/`: cero
ocurrencias. Los campos existen, el contrato los declara, y quedan vacíos en
todas las filas.

Importa más de lo que parece. Una foto sin hora ni lugar prueba que *alguien
subió una foto*. Con hora y lugar prueba que **esa** persona estuvo **ahí** a
**esa** hora — que es lo que una evidencia de campo tiene que probar cuando
alguien la discute meses después.

Se parte en dos mitades que no cuestan lo mismo:

| | Qué | Costo |
|---|---|---|
| **la hora** | `capturada_en_cliente`, del reloj del teléfono | Una columna en la cola local y un campo en el envío. Sin dependencias, sin permisos |
| **el lugar** | `metadatos_captura.gps` | Dependencia nueva, permiso de ubicación, y **una decisión de privacidad**: registrar el GPS del técnico en cada foto es geolocalizar a un empleado. No se hace en silencio |

La hora se puede hacer hoy. El lugar es **C** hasta que alguien decida, y la
decisión no es técnica.

*(Un matiz honesto sobre la hora: es el reloj del teléfono, que la persona
puede cambiar. No es un sello de tiempo confiable — es el dato que el campo
del backend pide, y su nombre lo dice: `capturada_en_**cliente**`. El servidor
ya guarda su propio `recibida_en_servidor`, y la distancia entre los dos es
información: una foto "tomada" tres horas después de recibida es una señal.)*

### 3.2 · `documento` abre la cámara · **A**

La aplicación distingue exactamente dos casos: `firma`, y todo lo demás. Todo
lo demás abre la cámara.

`documento` es un tipo de evidencia válido del backend. Una plantilla que pida
"copia del acta firmada" o "autorización del propietario" hoy le abre la
cámara al técnico y le pide que fotografíe un PDF.

### 3.3 · El esquema de evidencias sigue sin normalizar · deuda

Cuatro archivos lo leen directo. Es la misma forma del defecto que en los
campos del formulario apareció **cinco veces** y que se cerró creando
`CampoDelFormulario`. Ya está anotado en
[`CAMPO_RELEASE_CONTRACT.md`](CAMPO_RELEASE_CONTRACT.md) §6; se repite acá
porque cada cosa que se agregue a las evidencias lo empeora.

---

## 4 · Lo que bloquea antes que todo esto

**Producción tiene 2 migraciones de `campo`; esta rama tiene 6.** Las cuatro de
materiales —catálogo, kit, movimientos, actas e incidencias— **no están
aplicadas**.

O sea que el módulo entero de materiales, que en la aplicación está terminado y
probado, hoy no tiene tablas del otro lado. Eso bloquea la entrega antes de que
cualquier cosa de este documento importe.

---

## 5 · Orden sugerido

Por valor sobre costo, no por gravedad:

1. **3.1, la hora** — la mitad barata. Los campos ya existen del otro lado;
   falta adjuntarlos. Sin dependencias ni permisos.
2. **1.1 a 1.4** — un solo arreglo, dentro de un invariante que ya protege ese
   archivo. Alinear el vocabulario y darle a cada tipo su control.
3. **3.2** — `documento` necesita un selector de archivo, no una cámara.
4. **2.1** — primero la decisión, después el código. Es el que más valor tiene
   para quien usa la aplicación y el único que no se puede empezar escribiendo.

Fuera de esta lista, y antes de entregar: **§4**.

---

## 6 · Decisiones pendientes

Ninguna de estas la puede tomar una sesión:

| | Qué decidir |
|---|---|
| **D-1** | Qué significa "no se pudo hacer": estado propio, o resultado de completar. Y si cuenta como jornada hecha |
| **D-2** | Si se registra el GPS del técnico en cada evidencia. Es geolocalización de un empleado |
| **D-3** | Qué tipos de trabajo existen además de instalación y correctivo — y que son configuración por tenant, no código |
| **D-4** | Si las cuatro migraciones de materiales se aplican a producción, y cuándo |
