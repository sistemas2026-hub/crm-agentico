import '../../core/mock/field_mock_data.dart';
import 'estado_trabajo.dart';

/// Un trabajo, tal como lo muestra la lista.
///
/// Junta dos cosas que no se mezclan en ningún otro lado: lo que la orden trae
/// de verdad y lo que el diseño muestra pero el backend todavía no entrega.
/// Cada campo dice de dónde viene, y los futuros están agrupados en [futuro],
/// así que no hay forma de leer un dato de ejemplo creyendo que es real.
///
/// Esto **no** se guarda. La fila de `local_ordenes` no cambia: el día que la
/// API mande zona o prioridad, se cambia de dónde sale [futuro] y nada más.
class TrabajoVista {
  const TrabajoVista({
    required this.id,
    required this.numero,
    required this.estado,
    required this.clienteNombre,
    required this.direccion,
    required this.telefono,
    required this.tipoNombre,
    required this.tipoCodigo,
    required this.familia,
    required this.compromiso,
    required this.revision,
    required this.diagnosticoPrevio,
    required this.requiereActualizacion,
    required this.futuro,
  });

  // --- Datos reales, de la orden -------------------------------------------
  final String id;
  final int? numero;
  final EstadoTrabajo estado;
  final String clienteNombre;
  final String direccion;
  final String telefono;
  final String tipoNombre;
  final String tipoCodigo;
  final FamiliaTrabajo familia;
  final DateTime? compromiso;

  /// Version de la orden en el servidor. La transicion la manda como base para
  /// que el backend detecte si alguien la movio mientras tanto.
  final int revision;

  final String diagnosticoPrevio;

  /// La orden pide una versión más nueva de la aplicación.
  final bool requiereActualizacion;

  // --- Datos que todavía no existen ----------------------------------------
  /// Zona, prioridad, SLA y distancia. Se muestran; no filtran ni deciden.
  final TrabajoFuturoMock futuro;

  factory TrabajoVista.desdeOrden(Map<String, dynamic> orden) {
    final id = orden['id']?.toString() ?? '';
    final tipoCodigo = orden['tipo_codigo']?.toString() ?? '';
    final tipoNombre = orden['tipo_nombre']?.toString() ?? 'Trabajo';

    return TrabajoVista(
      id: id,
      numero: orden['numero'] is int
          ? orden['numero'] as int
          : int.tryParse(orden['numero']?.toString() ?? ''),
      estado: EstadoTrabajo.desde(orden['estado']?.toString()),
      clienteNombre: orden['cliente_nombre']?.toString() ?? 'Sin cliente',
      direccion: orden['direccion']?.toString() ?? 'Sin dirección',
      telefono: orden['telefono']?.toString() ?? '',
      tipoNombre: tipoNombre,
      tipoCodigo: tipoCodigo,
      familia: FamiliaTrabajo.desde(codigo: tipoCodigo, nombre: tipoNombre),
      compromiso: DateTime.tryParse(orden['fecha_compromiso']?.toString() ?? '')
          ?.toLocal(),
      revision: orden['revision'] as int? ?? 0,
      diagnosticoPrevio: orden['diagnostico_previo_ia']?.toString() ?? '',
      requiereActualizacion: (orden['schema_version'] as int? ?? 1) > 1,
      futuro: FieldMockData.trabajoFuturo(id),
    );
  }
}

/// De qué clase de trabajo se trata, para poder distinguirlos de un vistazo.
///
/// **No son entidades distintas del sistema**: una orden de trabajo es una
/// orden de trabajo, venga de una instalación nueva o de un ticket de soporte.
/// Esto solo cambia el icono y la palabra de la tarjeta. El tipo real es
/// `tipo_codigo`, que cada empresa define a su manera (la semilla del backend
/// trae `ftth_instalacion`), así que se reconoce por lo que el texto contiene y,
/// si no se reconoce, se muestra el nombre del tipo tal cual vino.
enum FamiliaTrabajo {
  instalacion,
  incidencia,
  mantenimiento,
  otro;

  static FamiliaTrabajo desde({required String codigo, required String nombre}) {
    final texto = '$codigo $nombre'.toLowerCase();
    if (texto.contains('instal') || texto.contains('alta')) {
      return FamiliaTrabajo.instalacion;
    }
    if (texto.contains('ticket') ||
        texto.contains('incidencia') ||
        texto.contains('correctivo') ||
        texto.contains('falla') ||
        texto.contains('soporte')) {
      return FamiliaTrabajo.incidencia;
    }
    if (texto.contains('mantenimiento') || texto.contains('preventivo')) {
      return FamiliaTrabajo.mantenimiento;
    }
    return FamiliaTrabajo.otro;
  }

  String get etiqueta => switch (this) {
        FamiliaTrabajo.instalacion => 'Instalación',
        FamiliaTrabajo.incidencia => 'Incidencia',
        FamiliaTrabajo.mantenimiento => 'Mantenimiento',
        FamiliaTrabajo.otro => 'Orden de trabajo',
      };
}
