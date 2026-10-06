import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/ejecucion/datos_de_ejecucion.dart';
import 'package:campo/features/ejecucion/ejecucion_screen.dart';
import 'package:flutter/material.dart';
import 'package:campo/core/widgets/dexter_app_header.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/fuente_de_ejecucion_falsa.dart';

/// La pantalla de ejecución, dibujada sin base y sin sesión.
///
/// POR QUÉ ESTO NO EXISTÍA ANTES
/// -----------------------------
/// Porque la pantalla leía SQLite y el almacenamiento seguro por su cuenta.
/// Montarla exigía levantar la base entera, y mezclar eso con pruebas de
/// widget ya colgó la suite de este proyecto una vez, así que la pantalla
/// donde el técnico pasa la mayor parte de su día era la única sin pruebas de
/// interfaz.
///
/// Ahora recibe [FuenteDeEjecucion]. En la aplicación es la base; acá es un
/// fixture con la misma forma —filas en `snake_case` y JSON en texto, como
/// llegan de verdad— para que lo que se prueba no sea una versión amable de
/// los datos.
void main() {
  Widget app(FuenteDeEjecucionFalsa fuente) => MaterialApp(
        theme: AppTheme.lightTheme,
        home: EjecucionScreen(
          ordenId: 'ot-1',
          fuente: fuente,
          // El chip de la cola tambien se inyecta: si no, consulta el
          // almacenamiento seguro al montarse y la prueba muere antes de
          // dibujar nada.
          resumenDeSync: const SyncSummary(
            status: SyncStatus.idle,
            isSyncing: false,
            hasConnectionError: false,
            mutacionesPendientes: 0,
            mutacionesConflicto: 0,
            evidenciasPendientes: 0,
            datosDirty: 0,
          ),
        ),
      );

  void pantallaAlta(WidgetTester tester) {
    tester.view.physicalSize = const Size(1000, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  group('1. Se dibuja con los datos que le dan', () {
    testWidgets('El formulario sale de la plantilla de la orden',
        (WidgetTester t) async {
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();

      expect(find.textContaining('4832'), findsWidgets);
      expect(find.textContaining('Potencia óptica en el equipo'), findsWidgets);
      expect(find.textContaining('Tipo de intervención'), findsWidgets);
    });

    testWidgets('Sin sesión no inventa una orden', (WidgetTester t) async {
      // Queda en su estado de carga. Dibujar una orden vacía seria peor:
      // alguien la completaria creyendo que es la suya.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(sinIdentidad: true)));
      await t.pumpAndSettle();

      expect(find.textContaining('Potencia óptica'), findsNothing);
    });

    testWidgets('Si la orden no bajó todavía, tampoco', (WidgetTester t) async {
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(sinOrden: true)));
      await t.pumpAndSettle();

      expect(find.textContaining('Potencia óptica'), findsNothing);
    });
  });

  group('2. Lo que se escribe se guarda apenas se escribe', () {
    testWidgets('Un campo de texto llega a la fuente sin apretar nada',
        (WidgetTester t) async {
      // Sin esperar a un botón "guardar": el teléfono se puede quedar sin
      // batería en mitad de un formulario.
      pantallaAlta(t);
      final FuenteDeEjecucionFalsa fuente = FuenteDeEjecucionFalsa();
      await t.pumpWidget(app(fuente));
      await t.pumpAndSettle();

      await t.enterText(find.byType(TextField).first, '-18.4');
      await t.pumpAndSettle();

      expect(fuente.guardados, isNotEmpty);
      // Se guarda como numero, no como texto: el campo es de tipo numero y
      // la pantalla lo convierte antes de persistirlo.
      expect(fuente.guardados.last['valor'].toString(), '-18.4');
      expect(fuente.resumenesRefrescados, greaterThan(0),
          reason: 'la cola tiene que volver a contar lo pendiente');
    });
  });

  group('3. Las reglas de cierre se pueden probar sin dibujar nada', () {
    // Viven en DatosDeEjecucion, no en el widget: son las que deciden si el
    // trabajo se puede dar por terminado.
    DatosDeEjecucion datos({
      Map<String, dynamic>? valores,
      List<Map<String, dynamic>>? evidencias,
      List<Map<String, dynamic>>? materiales,
    }) =>
        DatosDeEjecucion(
          orgId: 'org',
          profileId: 'perfil',
          orden: const <String, dynamic>{'numero': 4832, 'revision': 7},
          campos: FuenteDeEjecucionFalsa.camposTipicos,
          requisitosDeEvidencia: FuenteDeEjecucionFalsa.requisitosTipicos,
          valores: valores ?? <String, dynamic>{},
          evidenciasCapturadas: evidencias ?? <Map<String, dynamic>>[],
          materialesUsados: materiales ?? <Map<String, dynamic>>[],
        );

    // Estas reglas leen el esquema por `CampoDelFormulario`, que entiende el
    // vocabulario del servidor (`id`, `reglas.required`) y el viejo
    // (`clave`, `obligatorio`). Antes cada componente lo leia a su manera: el
    // formulario pintaba el asterisco rojo y el cierre no exigia el campo.
    test('Faltan los obligatorios vacíos, con su etiqueta', () {
      final List<String> faltan = datos().camposObligatoriosSinLlenar;

      expect(faltan, hasLength(2));
      expect(faltan, contains('Potencia óptica en el equipo del cliente'));
      expect(
        faltan,
        isNot(contains('Observaciones técnicas del empalme')),
        reason: 'ese campo no es obligatorio',
      );
    });

    test('Un obligatorio con espacios sigue estando vacío', () {
      final List<String> faltan = datos(
        valores: <String, dynamic>{'potencia_rx': '   '},
      ).camposObligatoriosSinLlenar;

      expect(faltan, contains('Potencia óptica en el equipo del cliente'));
    });

    test('La plantilla pide firma, y se nota si no está', () {
      expect(datos().exigeFirma, isTrue);
      expect(datos().hayFirma, isFalse);
    });

    test('Una firma tomada pero sin subir se distingue de una confirmada', () {
      // No es lo mismo: una firma que espera señal ya existe y el trabajo
      // puede cerrarse; una que no se tomó, no.
      final DatosDeEjecucion pendiente = datos(evidencias: <Map<String, dynamic>>[
        FuenteDeEjecucionFalsa.evidencia(
          requisitoId: 'firma_cliente',
          estado: 'pendiente',
        ),
      ]);
      final DatosDeEjecucion confirmada = datos(evidencias: <Map<String, dynamic>>[
        FuenteDeEjecucionFalsa.evidencia(requisitoId: 'firma_cliente'),
      ]);

      expect(pendiente.hayFirma, isTrue);
      expect(pendiente.firmaSinSubir, isTrue);
      expect(confirmada.hayFirma, isTrue);
      expect(confirmada.firmaSinSubir, isFalse);
    });

    test('Con todo hecho, el cierre deja de objetar', () {
      final DatosDeEjecucion completo = datos(
        valores: <String, dynamic>{
          'potencia_rx': '-18.4',
          'tipo_intervencion': 'Roseta / Conector',
        },
        evidencias: <Map<String, dynamic>>[
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'foto_roseta'),
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'foto_power_meter'),
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'firma_cliente'),
        ],
        materiales: <Map<String, dynamic>>[
          FuenteDeEjecucionFalsa.material(),
        ],
      );

      expect(completo.camposObligatoriosSinLlenar, isEmpty);
      expect(completo.cierre.puedeCerrar, isTrue);
    });

    test('Sin nada hecho, no', () {
      expect(datos().cierre.puedeCerrar, isFalse);
    });

    test('El número y la revisión salen de la fila, no de otro lado', () {
      // La revisión viaja en la transición para que el servidor detecte si
      // alguien movió la orden mientras tanto.
      expect(datos().numeroDeOrden, 4832);
      expect(datos().revision, 7);
    });
  });

  group('4. El esquema del servidor llega hasta la pantalla', () {
    testWidgets('Un campo de seleccion muestra sus opciones',
        (WidgetTester t) async {
      // El defecto original: el widget buscaba las opciones en `opciones` y el
      // servidor las manda en `reglas.options`, asi que un campo obligatorio
      // salia con "Sin opciones definidas" y no se podia responder.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();

      expect(find.text('Acometida / Drop'), findsOneWidget);
      expect(find.text('Roseta / Conector'), findsOneWidget);
      expect(find.textContaining('Sin opciones definidas'), findsNothing);
    });

    testWidgets('Una seleccion sin opciones dice que avisen a la oficina',
        (WidgetTester t) async {
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(
        campos: <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'roto',
            'titulo': 'Campo sin opciones',
            'tipo': 'seleccion',
            'reglas': <String, dynamic>{'required': true},
          },
        ],
      )));
      await t.pumpAndSettle();

      expect(find.textContaining('llegó sin opciones'), findsOneWidget);
      expect(find.textContaining('Avisá a la oficina'), findsOneWidget);
    });

    testWidgets('Un obligatorio vacio impide cerrar, y se dice cual',
        (WidgetTester t) async {
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();

      // Se afirma sobre el texto DEL CHECKLIST, no sobre la etiqueta del
      // campo. Esta prueba ya paso dos veces por la razon equivocada: una
      // encontrando "Falta la conformidad" (que es de la firma) y otra
      // encontrando el titulo del campo en el formulario de arriba, mientras
      // el checklist de datos seguia en verde con los obligatorios vacios.
      //
      // Dos y no tres: el booleano no lleva `required`, y el campo de
      // observaciones tampoco.
      expect(
        find.text('Faltan 2 campos'),
        findsOneWidget,
        reason: 'el checklist de datos tiene que objetar, y decir cuantos',
      );
    });

    testWidgets('Sin sesion dice que paso y ofrece salir',
        (WidgetTester t) async {
      // Antes quedaba en blanco para siempre: ni un mensaje ni una salida.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(sinIdentidad: true)));
      await t.pumpAndSettle();

      expect(find.text('No pudimos abrir este trabajo'), findsOneWidget);
      expect(find.text('Volver'), findsOneWidget);
    });
  });


  group('5. Finalizar y el checklist dicen lo mismo', () {
    /// Un kit de datos donde lo único que cambia es la respuesta.
    FuenteDeEjecucionFalsa conValores(Map<String, dynamic> valores) =>
        FuenteDeEjecucionFalsa(
          valores: valores,
          evidencias: <Map<String, dynamic>>[
            FuenteDeEjecucionFalsa.evidencia(requisitoId: 'foto_power_meter'),
            FuenteDeEjecucionFalsa.evidencia(requisitoId: 'foto_roseta'),
            FuenteDeEjecucionFalsa.evidencia(requisitoId: 'firma_cliente'),
          ],
          materiales: <Map<String, dynamic>>[FuenteDeEjecucionFalsa.material()],
        );

    testWidgets('Con un obligatorio vacío, ninguno de los dos deja cerrar',
        (WidgetTester t) async {
      pantallaAlta(t);
      // Todo menos la medicion: asi el que falta es UNO y el checklist lo
      // nombra, que es lo que esta prueba afirma.
      final FuenteDeEjecucionFalsa fuente = conValores(<String, dynamic>{
        'tipo_intervencion': 'Roseta / Conector',
      });
      await t.pumpWidget(app(fuente));
      await t.pumpAndSettle();

      // El checklist objeta, y nombra el campo cuando es uno solo.
      expect(
        find.text('Falta: Potencia óptica en el equipo del cliente'),
        findsOneWidget,
      );

      // …y el botón también, nombrando qué falta.
      await t.tap(find.text('Finalizar orden'));
      await t.pumpAndSettle();

      expect(fuente.transiciones, isEmpty, reason: 'no se cerró la orden');
      expect(find.byType(SnackBar), findsOneWidget);
    });

    testWidgets('Con algo que no es un número, tampoco',
        (WidgetTester t) async {
      // Este es el caso que antes se colaba: el checklist objetaba y el botón
      // cerraba igual, porque sólo miraba si el campo estaba vacío. La orden
      // se firmaba con una medición que no era una medición.
      //
      // Ya no se prueba con "-45": la medición perdió toda validación de
      // rango a propósito, porque es un registro de lo que marcó el power
      // meter. Lo que sigue sin servir es un texto que no es un número.
      pantallaAlta(t);
      final FuenteDeEjecucionFalsa fuente = conValores(<String, dynamic>{
        'tipo_intervencion': 'Roseta / Conector',
        'potencia_rx': 'sin lectura',
      });
      await t.pumpWidget(app(fuente));
      await t.pumpAndSettle();

      expect(
        find.text('Falta: Potencia óptica en el equipo del cliente'),
        findsOneWidget,
        reason: 'un valor que no sirve cuenta como faltante, no como hecho',
      );

      await t.tap(find.text('Finalizar orden'));
      await t.pumpAndSettle();

      expect(
        fuente.transiciones,
        isEmpty,
        reason: 'un -45 dBm donde el esquema pide entre -30 y -5 no se firma',
      );
    });

    testWidgets('Con todo válido, los dos permiten', (WidgetTester t) async {
      pantallaAlta(t);
      final FuenteDeEjecucionFalsa fuente = conValores(<String, dynamic>{
        'tipo_intervencion': 'Roseta / Conector',
        'potencia_rx': '-18.4',
      });
      await t.pumpWidget(app(fuente));
      await t.pumpAndSettle();

      expect(find.textContaining('Falta'), findsNothing,
          reason: 'el checklist no tiene nada que objetar');

      await t.tap(find.text('Finalizar orden'));
      await t.pumpAndSettle();

      expect(fuente.transiciones, hasLength(1));
      expect(fuente.transiciones.first['estado'], 'completada_pendiente_sync');
      expect(fuente.transiciones.first['revision_base'], 7,
          reason: 'la revisión viaja para que el servidor detecte cambios');
    });

    testWidgets('Un error de plantilla no deja cerrar, y no culpa al técnico',
        (WidgetTester t) async {
      pantallaAlta(t);
      final FuenteDeEjecucionFalsa fuente = FuenteDeEjecucionFalsa(
        campos: <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'roto',
            'titulo': 'Campo sin opciones',
            'tipo': 'seleccion',
            'reglas': <String, dynamic>{'required': true},
          },
        ],
        evidencias: <Map<String, dynamic>>[
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'foto_power_meter'),
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'foto_roseta'),
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'firma_cliente'),
        ],
        materiales: <Map<String, dynamic>>[FuenteDeEjecucionFalsa.material()],
      );
      await t.pumpWidget(app(fuente));
      await t.pumpAndSettle();

      await t.tap(find.text('Finalizar orden'));
      await t.pumpAndSettle();

      expect(fuente.transiciones, isEmpty);
      // El mensaje habla de la plantilla, no de lo que el técnico dejó sin
      // hacer: no puede responder ese campo por más que quiera.
      expect(find.textContaining('Avisá a la oficina'), findsWidgets);
    });
  });

  group('5b. La medicion se registra; el veredicto lo da la OLT', () {
    testWidgets('La franja de arriba dice QUE falta, sin bajar el scroll',
        (WidgetTester t) async {
      // Con una mano, en una escalera, bajar hasta el checklist del fondo para
      // saber que falta es un viaje -- y si no se baja, el tecnico se entera
      // cuando toca «completar» y el boton no lo deja.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();

      // Nombra QUE falta, no cuantos: «te faltan 2» obliga a bajar igual.
      expect(find.textContaining('Falta: '), findsOneWidget);
    });

    testWidgets('Sin nada pendiente, la franja NO ocupa lugar',
        (WidgetTester t) async {
      // Una franja que dice «todo listo» permanentemente ocupa el lugar donde
      // el tecnico mira cuando SI falta algo, y deja de leerse.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(
        requisitos: const <Map<String, dynamic>>[],
        campos: const <Map<String, dynamic>>[],
      )));
      await t.pumpAndSettle();

      expect(find.textContaining('Falta: '), findsNothing);
    });

    testWidgets('Una señal mala se puede registrar, no se bloquea',
        (WidgetTester t) async {
      // -27 dBm es una señal fuera de rango, medida bien, y suele ser el
      // motivo mismo de la visita. Si el umbral de ACEPTACION bloqueara, el
      // tecnico no podria anotarla: habria que mentir o no cerrar la orden.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(
        valores: <String, dynamic>{
          'potencia_rx': '-27',
          'tipo_intervencion': 'Roseta / Conector',
        },
      )));
      await t.pumpAndSettle();

      expect(find.textContaining('Tiene que ser'), findsNothing);
      // Lo que esta linea quiere decir es que el CHECKLIST no marque el
      // formulario como incompleto por esta lectura. Decia `'Falta:'` a secas y
      // eso dejo de servir cuando entro la franja fija de «lo que falta», que
      // nombra lo que de verdad falta en esta orden --las fotos-- y es
      // correcto. Se nombra el campo, que es lo que la prueba mide.
      expect(
        find.textContaining('Potencia óptica en el equipo del cliente',
            skipOffstage: false),
        findsOneWidget,
        reason: 'el campo se dibuja',
      );
      expect(
        find.textContaining('Falta: Potencia óptica'),
        findsNothing,
        reason: 'una lectura mala no puede contar como campo sin llenar',
      );
    });

    testWidgets('NINGUN valor se rechaza: es un registro, no una respuesta',
        (WidgetTester t) async {
      // El campo perdio toda validacion de rango a proposito. Ya paso dos
      // veces que un umbral rechazara una lectura real: primero "-30 a -5"
      // citando un umbral de aceptacion, despues "-40 a -5" como guarda de
      // tipeo. Un registro no se aprueba: se anota.
      pantallaAlta(t);
      for (final String medido in <String>['-45', '-3', '0', '12.5']) {
        await t.pumpWidget(app(FuenteDeEjecucionFalsa(
          valores: <String, dynamic>{'potencia_rx': medido},
        )));
        await t.pumpAndSettle();
        expect(find.textContaining('Tiene que ser'), findsNothing,
            reason: '$medido no puede rechazarse');
      }
    });

    testWidgets('Pero lo que NO es un numero se sigue diciendo',
        (WidgetTester t) async {
      // Sacar el rango no es aceptar cualquier cosa: 'abc' no es una
      // medicion, y guardarlo como si lo fuera es peor que avisar.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(
        valores: <String, dynamic>{'potencia_rx': 'abc'},
      )));
      await t.pumpAndSettle();

      expect(find.textContaining('Tiene que ser un número'), findsOneWidget);
    });

    testWidgets('La lectura de la OLT se ve ARRIBA de la medicion del tecnico',
        (WidgetTester t) async {
      // Las dos sirven mas juntas: si difieren mucho, el problema esta entre
      // la central y el equipo. Estaban en pantallas distintas y habia que
      // memorizar un numero y volver.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();

      expect(find.text('LO QUE VE LA OLT'), findsOneWidget);
      expect(find.text('-21.19 dBm'), findsOneWidget);
      expect(find.text('ACEPTABLE'), findsOneWidget);

      // Y ARRIBA DEL CUADRO donde se escribe, no debajo: una referencia
      // debajo se lee como el resultado de lo que se acaba de anotar.
      final double laDeLaOlt = t.getTopLeft(find.text('-21.19 dBm')).dy;
      final double dondeSeEscribe =
          t.getTopLeft(find.byType(TextField).last).dy;
      expect(laDeLaOlt, lessThan(dondeSeEscribe),
          reason: 'la lectura de la OLT va antes del cuadro de la medicion');

      // Y DENTRO del bloque de ese campo: debajo de su rotulo, no flotando
      // arriba de todo el formulario.
      final double elRotulo =
          t.getTopLeft(find.textContaining('Potencia óptica en el equipo')).dy;
      expect(laDeLaOlt, greaterThan(elRotulo));
    });

    testWidgets('Sin lectura en la ficha no se dibuja ningun hueco',
        (WidgetTester t) async {
      // La ficha puede venir sin equipo. Decirlo es cosa de la pantalla de
      // detalle, que ya lo hace; aca un guion o una caja vacia solo agregan
      // ruido arriba del campo que hay que responder.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(sinContexto: true)));
      await t.pumpAndSettle();

      expect(find.text('LO QUE VE LA OLT'), findsNothing);
      expect(find.textContaining('medida '), findsNothing);
      // Pero el campo sigue estando: se mide igual.
      expect(find.textContaining('Potencia óptica en el equipo'), findsWidgets);
    });

    testWidgets('La ayuda no afirma un umbral propio',
        (WidgetTester t) async {
      // Habia CUATRO rangos distintos en el sistema, y este era uno: la
      // ayuda decia "-15 a -25 dBm" mientras el motor evaluaba con -8 a -25.
      // Dos pantallas de la misma orden daban respuestas distintas sobre la
      // misma señal.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();

      expect(find.textContaining('-15 a -25'), findsNothing);
      expect(find.textContaining('Umbral de aceptación:'), findsNothing);
      // Y dice que es lo que se anota.
      expect(find.textContaining('Queda como registro'), findsOneWidget);
    });
  });

  group('6. El error se ve en el campo, no sólo en el resumen', () {
    testWidgets('Un valor que no es un número muestra su motivo al lado',
        (WidgetTester t) async {
      // El motivo va PEGADO al campo, no sólo en el resumen de abajo: el
      // técnico corrige donde escribió, no donde se lo recuerdan.
      //
      // Ya no se prueba con "-45": la medición perdió toda validación de
      // rango a propósito. Lo que sigue sin servir es un texto que no es un
      // número.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(
        valores: <String, dynamic>{
          'potencia_rx': 'sin lectura',
        },
      )));
      await t.pumpAndSettle();

      expect(find.textContaining('Tiene que ser un número'), findsOneWidget);
    });

    testWidgets('Un valor bueno no muestra ningún motivo',
        (WidgetTester t) async {
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(
        valores: <String, dynamic>{
          'potencia_rx': '-18.4',
        },
      )));
      await t.pumpAndSettle();

      expect(find.textContaining('Tiene que ser'), findsNothing);
    });
  });

  group('7. La cabecera dice de quién es el trabajo y en qué paso va', () {
    testWidgets('Cliente y paso, con datos que ya existen',
        (WidgetTester t) async {
      // La pantalla es larga y se abre desde una lista: a tres bloques de
      // scroll ya no se sabe de qué orden se trata.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();

      expect(find.text('Carlos Gómez Rincón'), findsOneWidget);
      // El paso vive en el encabezado de paso del diseño, y se escribe con
      // su tipografía. Estaba dos veces en la misma pantalla.
      expect(find.text('PASO 3 DE 5'), findsOneWidget,
          reason: 'la orden está en sitio, que es el tercer paso');
      expect(find.text('Paso 3 de 5'), findsNothing);
    });

    testWidgets('El paso NO es el "2 de 5" fijo de la maqueta',
        (WidgetTester t) async {
      // Las cuatro pantallas de paso del diseño dicen todas "PASO 2 DE 5" y
      // pintan la barra al 2/5: Stitch repitió el mismo encabezado sin variar
      // el número. Copiar ese 2 habría puesto el mismo paso en todas las
      // órdenes, sin importar dónde estuvieran de verdad.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();

      expect(find.text('PASO 2 DE 5'), findsNothing);

      // Y la barra de avance del encabezado sigue al paso real: 3 de 5.
      final DexterStepHeader encabezado =
          t.widget<DexterStepHeader>(find.byType(DexterStepHeader));
      expect(encabezado.paso, 3);
      expect(encabezado.deTotal, 5);
    });
  });

  group('7b. La evidencia dice cuánto falta, y qué pasa sin señal', () {
    testWidgets('El progreso se cuenta, no se afirma',
        (WidgetTester t) async {
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();

      // Sin ninguna foto tomada todavía: cero de las que pide la orden.
      //
      // NO DICE «CARGADAS». Decia «Fotos cargadas: 0/2» arriba y «0
      // capturadas» abajo: dos palabras para dos hechos distintos, y
      // «cargada» se lee como que el servidor ya la tiene. Ahora los dos
      // numeros van juntos y separados.
      expect(find.textContaining('Fotos de esta orden:'), findsOneWidget);
      expect(find.textContaining('cargadas'), findsNothing);
      expect(find.text('0%'), findsOneWidget);
      expect(
        find.text('0/3 capturadas · 0/3 enviadas'),
        findsOneWidget,
        reason: 'las dos cuentas SIEMPRE, incluso en cero: el caso en que '
            'ninguna salio del telefono es justo el que no puede callarse',
      );
    });

    testWidgets('El aviso sin señal no promete un cifrado que no existe',
        (WidgetTester t) async {
      // La maqueta escribe "memoria cifrada interna del terminal" y
      // sincronización "al detectar enlace 4G LTE o red Wi-Fi autorizada".
      // Ninguna de las dos cosas es cierta en esta aplicación, y una promesa
      // de cifrado que no existe es peor que no decir nada.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();

      expect(find.text('SIN COBERTURA NO SE PIERDE'), findsOneWidget);
      expect(find.textContaining('cifrada'), findsNothing);
      expect(find.textContaining('4G'), findsNothing);
      expect(find.textContaining('se envían solas'), findsOneWidget);
    });
  });


  group('8. La interfaz no depende del formato del JSON', () {
    /// La misma plantilla escrita en los dos vocabularios.
    List<Map<String, dynamic>> comoElServidor() => <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'tipo_intervencion',
            'titulo': 'Tipo de intervención física',
            'tipo': 'seleccion',
            'reglas': <String, dynamic>{
              'required': true,
              'options': <String>['Acometida / Drop', 'Roseta / Conector'],
            },
          },
        ];

    List<Map<String, dynamic>> comoElFormatoViejo() => <Map<String, dynamic>>[
          <String, dynamic>{
            'clave': 'tipo_intervencion',
            'etiqueta': 'Tipo de intervención física',
            'tipo': 'seleccion',
            'obligatorio': true,
            'opciones': <String>['Acometida / Drop', 'Roseta / Conector'],
          },
        ];

    Future<void> montar(
      WidgetTester t,
      List<Map<String, dynamic>> campos,
    ) async {
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(campos: campos)));
      await t.pumpAndSettle();
    }

    testWidgets('Con el formato del servidor se dibuja igual',
        (WidgetTester t) async {
      await montar(t, comoElServidor());

      // textContaining: el bloque antepone el numero de campo ("1. ...").
      expect(
        find.textContaining('Tipo de intervención física'),
        findsWidgets,
      );
      expect(find.text('Acometida / Drop'), findsOneWidget);
      expect(find.text('Roseta / Conector'), findsOneWidget);
    });

    testWidgets('Y con una orden vieja guardada, tambien',
        (WidgetTester t) async {
      // Una orden que ya esta en el telefono tiene que seguir abriendose: al
      // tecnico no se le puede pedir que resincronice para poder trabajar.
      await montar(t, comoElFormatoViejo());

      expect(
        find.textContaining('Tipo de intervención física'),
        findsWidgets,
      );
      expect(find.text('Acometida / Drop'), findsOneWidget);
      expect(find.text('Roseta / Conector'), findsOneWidget);
    });

    testWidgets('Los dos formatos bloquean el cierre por lo mismo',
        (WidgetTester t) async {
      for (final List<Map<String, dynamic>> campos in <List<Map<String, dynamic>>>[
        comoElServidor(),
        comoElFormatoViejo(),
      ]) {
        await montar(t, campos);
        expect(
          find.text('Falta: Tipo de intervención física'),
          findsOneWidget,
          reason: 'el checklist dice lo mismo con los dos vocabularios',
        );
      }
    });
  });

}
