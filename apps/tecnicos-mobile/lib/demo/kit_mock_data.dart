/// ESTO NO ES PRODUCTO. Son valores de ejemplo. Ver `lib/demo/LEEME.md`.
/// CAMPO-DATA-025 · El material que el técnico tiene a cargo.
///
/// El diseño de Stitch muestra la custodia completa: consumibles, bobinas
/// fraccionables, equipos serializados y fijaciones. **Nada de esto existe
/// todavía**: no hay modelo, ni API, ni cola offline para movimientos de
/// material. Es la especificación de lo que hay que construir (Fase 8).
///
/// Como todo lo de ejemplo, se ve solo con el modo demostración encendido, no
/// descuenta inventario, no persiste movimientos y no genera actas.
///
/// DESDE LA FASE DE MATERIALES esto es SOLO el ejemplo. La custodia real
/// existe: `MaterialEnCustodia` se mudó a
/// `features/materiales/material_en_custodia.dart`, y la pantalla lee la
/// base local. Lo de acá se ve únicamente con el modo demostración
/// encendido, para poder enseñar la aplicación sin una jornada cargada.
library;

// Se importa el tipo del dominio, pero NO se re-exporta: el ejemplo es un
// usuario de esa forma, no su via de acceso. Reexportarlo haria que una
// pantalla terminara dependiendo del archivo de mock para conocer un tipo de
// la operacion real, que es exactamente al reves de como debe ser.
import '../../features/materiales/material_en_custodia.dart';

class KitMockData {
  const KitMockData._();

  static const String deposito = 'Depósito Central #02';

  /// CAMPO-DATA-051 · El acta con la que se entregó el kit y quién la firmó.
  /// Futuro: inventario de Dexter (`kit.acta`, `kit.despachado_por`).
  static const String acta = 'Acta #K-2024-094';
  static const String despachadoPor = 'M. Morales (Almacén)';
  static const String horaDespacho = '07:15 AM';

  /// CAMPO-DATA-052 · Lo que identifica a un equipo serializado además del
  /// número de serie, y en qué estado llegó.
  /// Futuro: inventario de Dexter (`equipo.mac`, `equipo.estado_previo`).
  static const String macEquipo = '48:57:54:A9:B0:C1';
  static const String estadoPrevioEquipo = 'Validado OLT';
  static const String ingresoAFurgon = 'Hoy 07:12 AM';
  static const String jornada = 'Jornada 24-Feb';
  static const int incidencias = 0;

  static const List<MaterialEnCustodia> items = <MaterialEnCustodia>[
    MaterialEnCustodia(
      categoria: 'Consumible Telecom',
      nombre: 'Conector SC/APC Rápido Verde',
      detalle: 'Pigtails mecánicos universales',
      clase: ClaseMaterial.consumible,
      recibidos: 10,
      usados: 3,
      unidad: 'unidades',
      ordenesRelacionadas: <String>['OT #4832', '#4830'],
      razon: '2 Altas + 1 Reparación',
    ),
    MaterialEnCustodia(
      categoria: 'Bobina Fraccionable',
      nombre: 'Cable Drop Fibra 1 Hilo G657A2',
      detalle: 'Metraje remanente en camioneta',
      clase: ClaseMaterial.bobina,
      recibidos: 120,
      usados: 35,
      unidad: 'm',
      ultimoMovimiento: 'Último tramo: 35m en OT #4831',
    ),
    MaterialEnCustodia(
      categoria: 'Activo Serializado',
      nombre: 'ONT Huawei EchoLife HG8145V5',
      detalle: 'Dual Band WiFi GPON',
      clase: ClaseMaterial.serializado,
      recibidos: 2,
      usados: 1,
      unidad: 'unidades',
      serie: '48575443-A190C',
      ultimoMovimiento: 'Asignado previo: Bodega Dep. 02 · 1 instalada en OT #4830',
    ),
    MaterialEnCustodia(
      categoria: 'Caja Terminal Cliente',
      nombre: 'Roseta Óptica de Pared + Pigtail',
      detalle: 'Recibidas: 4 · Instaladas: 1',
      clase: ClaseMaterial.terminal,
      recibidos: 4,
      usados: 1,
      unidad: 'unidades',
    ),
    MaterialEnCustodia(
      categoria: 'Fijación de cableado',
      nombre: 'Precintos y Grapas para Drop',
      detalle: 'Recibidos: 50 · Usados: 18',
      clase: ClaseMaterial.consumible,
      recibidos: 50,
      usados: 18,
      unidad: 'unidades',
    ),
  ];

  /// CAMPO-DATA-025 · En qué punto de la cadena está el material y qué se
  /// sabe de cada paso.
  static const List<(String, String)> custodia = <(String, String)>[
    ('Bodega', horaDespacho),
    ('Técnico (Tú)', 'En custodia'),
    ('OTs Campo', 'En progreso'),
    ('Cierre', 'Pendiente'),
  ];

  /// Lo que el cierre de jornada dice que quedó cuadrado.
  static const List<String> conciliacion = <String>[
    '3 OTs Descargadas',
    'ONT Serial Cuadrado',
  ];
}
