// LA MARCA DEL TELÉFONO DICE LO MISMO QUE LA DEL SERVIDOR (13/11/2026).
//
// Cada caso de la familia A repite uno de `campo/tests/test_marca_de_agua.py`
// con los mismos datos y la misma afirmación. Si alguien cambia una regla de
// un lado, este archivo o aquel es el que se pone rojo: la vista previa no
// puede prometer una banda distinta de la que el servidor estampa.
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:campo/core/marca/marca_de_agua.dart';
import 'package:campo/core/marca/marca_de_agua_local.dart';

const ConfiguracionDeMarca todo = ConfiguracionDeMarca(
  activa: true,
  mostrarEmpresa: true,
  mostrarTecnico: true,
  mostrarCoordenadas: true,
  mostrarFecha: true,
  mostrarLogo: false,
  opacidad: 55,
  posicion: 'abajo_izquierda',
);

DatosDeLaFoto datos({
  Map<String, dynamic>? metadatos,
  bool esCaptura = false,
  bool esFirma = false,
}) =>
    DatosDeLaFoto(
      empresa: 'Rapilink SAS',
      tecnico: 'Carlos Pérez',
      fecha: DateTime.utc(2026, 11, 12, 20, 30),
      metadatos: metadatos ??
          const <String, dynamic>{
            'lat': 10.9108,
            'lng': -74.8186,
            'precision_m': 8,
          },
      esCaptura: esCaptura,
      esFirma: esFirma,
    );

String texto(ConfiguracionDeMarca c, DatosDeLaFoto d) =>
    lineasDe(c, d).join(' | ');

void main() {
  group('A. qué dice (espejo de test_marca_de_agua.py)', () {
    test('a1 las cuatro líneas, y la fecha en Bogotá', () {
      final String t = texto(todo, datos());
      expect(t, contains('Rapilink SAS'));
      expect(t, contains('Carlos Pérez'));
      expect(t, contains('10.910800'));
      expect(t, contains('-74.818600'));
      //  20:30 UTC son las 15:30 en Bogotá, esté el teléfono en la zona que
      //  esté.
      expect(t, contains('12/11/2026 15:30'));
    });

    test('a2 lo que la empresa apaga no aparece', () {
      final String t = texto(
          todo.copyWith(mostrarTecnico: false, mostrarCoordenadas: false),
          datos());
      expect(t, contains('Rapilink SAS'));
      expect(t, isNot(contains('Carlos')));
      expect(t, isNot(contains('10.9')));
    });

    test('a3 una foto de galería no lleva coordenadas, y lo dice', () {
      final String t = texto(
          todo,
          datos(metadatos: <String, dynamic>{
            'lat': 10.9108,
            'lng': -74.8186,
            'de_galeria': true,
          }));
      expect(t, isNot(contains('10.9')));
      expect(t.toLowerCase(), contains('galeria'));
    });

    test('a4 sin GPS dice por qué y nunca 0,0', () {
      final String t = texto(todo,
          datos(metadatos: <String, dynamic>{'ubicacion_motivo': 'permiso_denegado'}));
      expect(t, contains('Sin ubicacion'));
      expect(t, contains('sin permiso de ubicacion'));
      expect(t, isNot(contains('0, 0')));
      expect(t, isNot(contains('0.000000')));
    });

    test('a5 una ubicación simulada se dice, sin acusar', () {
      final String t = texto(
          todo,
          datos(metadatos: <String, dynamic>{
            'lat': 10.9108,
            'lng': -74.8186,
            'ubicacion_simulada': true,
          }));
      expect(t, contains('no verificada'));
      expect(t, isNot(contains('SIMULADA')));
    });

    for (final List<Object?> c in <List<Object?>>[
      <Object?>[8, '10.910800', null],
      <Object?>[120, '10.9108', '10.910800'],
      <Object?>[2000, '10.911', '10.9108'],
    ]) {
      test('a6 los decimales siguen a la precisión (±${c[0]} m)', () {
        final String t = texto(
            todo,
            datos(metadatos: <String, dynamic>{
              'lat': 10.9108,
              'lng': -74.8186,
              'precision_m': c[0],
            }));
        expect(t, contains(c[1]! as String));
        if (c[2] != null) expect(t, isNot(contains(c[2]! as String)));
        expect(t, contains('±${c[0]} m'));
      });
    }

    test('d1 el motivo de ubicación NO se imprime crudo', () {
      final String veneno = '${'X' * 160} cedula 1012345678 tel 3150000000';
      final String t = texto(
          todo, datos(metadatos: <String, dynamic>{'ubicacion_motivo': veneno}));
      expect(t, isNot(contains('1012345678')));
      expect(t, isNot(contains('3150000000')));
      expect(t, isNot(contains('XXX')));
      expect(t, contains('Sin ubicacion'));
    });

    for (final List<String> c in <List<String>>[
      <String>['servicio_apagado', 'GPS apagado'],
      <String>['permiso_denegado', 'sin permiso'],
      <String>['sin_senal_gps', 'señal GPS'],
      <String>['error_TimeoutException', 'error del sistema'],
    ]) {
      test('d2 el motivo ${c[0]} sigue diciendo algo', () {
        expect(
            texto(todo,
                datos(metadatos: <String, dynamic>{'ubicacion_motivo': c[0]})),
            contains(c[1]));
      });
    }
  });

  group('B. cuándo no hay banda', () {
    test('apagada', () {
      expect(seEstampa(todo.copyWith(activa: false), datos()), isFalse);
      expect(seEstampa(ConfiguracionDeMarca.apagada, datos()), isFalse);
    });

    test('la firma del cliente nunca', () {
      expect(seEstampa(todo, datos(esFirma: true)), isFalse);
      expect(esRequisitoDeFirma('firma_receptor'), isTrue);
      expect(esRequisitoDeFirma('firma_del_titular'), isTrue);
      expect(esRequisitoDeFirma('onu_instalada'), isFalse);
    });

    test('una captura, solo si la empresa lo pide', () {
      expect(seEstampa(todo, datos(esCaptura: true)), isFalse);
      expect(seEstampa(todo.copyWith(estamparCapturas: true),
          datos(esCaptura: true)), isTrue);
    });

    test('sin nada que decir, no hay banda', () {
      const ConfiguracionDeMarca nada = ConfiguracionDeMarca(activa: true);
      expect(seEstampa(nada, datos()), isFalse);
      expect(
          seEstampa(nada.copyWith(mostrarLogo: true), datos(), hayLogo: true),
          isTrue);
    });

    test('lo dudoso que llega del servidor cae a apagado', () {
      final ConfiguracionDeMarca c = ConfiguracionDeMarca.fromJson(
          <String, dynamic>{'activa': 'si', 'mostrar_empresa': 1});
      expect(c.activa, isFalse);
      expect(c.mostrarEmpresa, isFalse);
    });
  });

  group('C. la banda tiene las medidas del servidor', () {
    test('a la derecha es una sola regla (espejo de test_e2)', () {
      expect(aLaDerecha('abajo_derecha'), isTrue);
      expect(aLaDerecha('arriba_derecha'), isTrue);
      expect(aLaDerecha('abajo_izquierda'), isFalse);
      expect(aLaDerecha(''), isFalse);
    });

    test('las medidas de _dibujar, número por número', () {
      //  1920×1080: lado corto 1080 → unidad int(59.4)=59, letra
      //  int(35.64)=35, margen int(12.96)=12.
      final MedidasDeBanda m = MedidasDeBanda.para(const Size(1920, 1080), 3);
      expect(m.alto, 59 * 3);
      expect(m.letra, 35);
      expect(m.margen, 12);

      //  Foto chica: los pisos de 11 y 8 del servidor.
      final MedidasDeBanda chica = MedidasDeBanda.para(const Size(320, 240), 1);
      expect(chica.letra, 11);
      expect(chica.margen, 8);
    });
  });

  group('D. el widget', () {
    Widget montar(ConfiguracionDeMarca c, DatosDeLaFoto d, Uint8List png) =>
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 400,
              height: 300,
              child: FotoConMarca(
                imagen: MemoryImage(png),
                configuracion: c,
                datos: d,
              ),
            ),
          ),
        );

    testWidgets('prendida, la banda aparece con sus líneas', (WidgetTester t) async {
      await t.runAsync(() async {
        final Uint8List png = await _pngReal(320, 240);
        await t.pumpWidget(montar(todo, datos(), png));
        await precacheImage(
            MemoryImage(png), t.element(find.byType(Scaffold)));
        await Future<void>.delayed(const Duration(milliseconds: 50));
      });
      await t.pump();
      await t.pump();
      expect(find.byKey(const ValueKey<String>('banda_de_marca')), findsOneWidget);
      expect(find.text('Rapilink SAS'), findsOneWidget);
    });

    testWidgets('apagada, no hay banda', (WidgetTester t) async {
      await t.runAsync(() async {
        final Uint8List png = await _pngReal(320, 240);
        await t.pumpWidget(montar(todo.copyWith(activa: false), datos(), png));
        await precacheImage(
            MemoryImage(png), t.element(find.byType(Scaffold)));
        await Future<void>.delayed(const Duration(milliseconds: 50));
      });
      await t.pump();
      await t.pump();
      expect(find.byKey(const ValueKey<String>('banda_de_marca')), findsNothing);
    });

    testWidgets('sobre la firma, no hay banda', (WidgetTester t) async {
      await t.runAsync(() async {
        final Uint8List png = await _pngReal(320, 240);
        await t.pumpWidget(montar(todo, datos(esFirma: true), png));
        await precacheImage(
            MemoryImage(png), t.element(find.byType(Scaffold)));
        await Future<void>.delayed(const Duration(milliseconds: 50));
      });
      await t.pump();
      await t.pump();
      expect(find.byKey(const ValueKey<String>('banda_de_marca')), findsNothing);
    });
  });

  group('E. lo guardado en el teléfono', () {
    test('sin nada guardado, la apagada; nunca lanza', () async {
      final Directory tmp = await Directory.systemTemp.createTemp('marca_local');
      final MarcaDeAguaLocal local = MarcaDeAguaLocal(raiz: () async => tmp);
      final MarcaDeLaEmpresa m = await local.leer('org-1');
      expect(m.configuracion.activa, isFalse);
      await tmp.delete(recursive: true);
    });

    test('lo de una empresa no se lee desde otra', () async {
      final Directory tmp = await Directory.systemTemp.createTemp('marca_local');
      final Directory dirA = Directory('${tmp.path}/marca_de_agua/org-a');
      await dirA.create(recursive: true);
      await File('${dirA.path}/marca.json').writeAsString(
          '{"configuracion":{"activa":true,"mostrar_empresa":true},'
          '"empresa":"A","tecnico":"Ana","logo_version":null}');
      final MarcaDeAguaLocal local = MarcaDeAguaLocal(raiz: () async => tmp);

      expect((await local.leer('org-a')).configuracion.activa, isTrue);
      expect((await local.leer('org-b')).configuracion.activa, isFalse);
      //  Un id con barras no se escapa de su carpeta.
      expect((await local.leer('../org-a')).configuracion.activa, isFalse);
      await tmp.delete(recursive: true);
    });
  });
}

/// Una imagen real, dibujada con el motor de Flutter: nada de archivos
/// binarios en el repo, y nada de bytes escritos a mano que el decodificador
/// pueda rechazar.
Future<Uint8List> _pngReal(int ancho, int alto) async {
  final ui.PictureRecorder grabadora = ui.PictureRecorder();
  Canvas(grabadora).drawRect(
    Rect.fromLTWH(0, 0, ancho.toDouble(), alto.toDouble()),
    Paint()..color = const Color(0xFF285AA0),
  );
  final ui.Image img = await grabadora.endRecording().toImage(ancho, alto);
  final ByteData? b = await img.toByteData(format: ui.ImageByteFormat.png);
  return b!.buffer.asUint8List();
}
