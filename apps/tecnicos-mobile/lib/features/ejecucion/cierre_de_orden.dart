/// Qué falta para poder cerrar un trabajo, y qué no.
///
/// POR QUÉ ESTO ES LÓGICA PURA
/// ---------------------------
/// Es la cuenta que decide si un técnico puede decir "terminé". Vive fuera de
/// la pantalla para poder probarla sin cámara, sin base y sin emulador —
/// exactamente como `progreso_evidencias`, y por el mismo motivo: si la
/// decisión vive dentro de un widget, la única forma de verificarla es a mano.
///
/// LA REGLA QUE NO SE NEGOCIA
/// --------------------------
/// **Lo obligatorio lo decide Dexter, no la aplicación.** El teléfono no sabe
/// qué exige cada tipo de trabajo; recibe esa lista en el esquema y la
/// respeta. Una app que decidiera por su cuenta qué es imprescindible se
/// desincronizaría del backend el día que una empresa cambie su formulario, y
/// dejaría cerrar trabajos que el servidor va a rechazar después — con el
/// técnico ya en la casa siguiente.
///
/// LO PENDIENTE DE SUBIR NO IMPIDE CERRAR
/// --------------------------------------
/// Un trabajo terminado sin señal está terminado. La cola sube sola cuando
/// haya red, y bloquear el cierre por eso dejaría a la cuadrilla esperando
/// señal en la puerta del cliente. Se muestra, eso sí, porque el técnico tiene
/// que saber que su jornada todavía no llegó a la oficina.
library;

/// En qué estado está cada cosa que hay que mirar antes de cerrar.
enum EstadoDeRequisito {
  /// Hecho.
  completo,

  /// Falta, y es obligatorio: impide cerrar.
  pendiente,

  /// Falta, pero es opcional: se muestra y no bloquea.
  opcional,

  /// Hecho, pero todavía no llegó al servidor. No bloquea.
  sinSubir,

  /// El servidor lo devolvió marcado: un descuadre, un equipo repetido.
  /// No bloquea el cierre del trabajo, pero no puede pasar desapercibido.
  conConflicto,
}

/// Una línea del checklist.
class RequisitoDeCierre {
  const RequisitoDeCierre({
    required this.titulo,
    required this.estado,
    this.detalle = '',
  });

  final String titulo;
  final EstadoDeRequisito estado;
  final String detalle;

  bool get bloquea => estado == EstadoDeRequisito.pendiente;
}

/// El checklist completo: siempre las mismas líneas, en el mismo orden.
///
/// Determinista a propósito. Un checklist cuyo contenido cambia de orden o
/// aparece y desaparece según el caso obliga a leerlo entero cada vez; uno
/// estable se mira de un vistazo, que es lo que alguien hace parado en una
/// vereda.
class CierreDeOrden {
  const CierreDeOrden(this.requisitos);

  final List<RequisitoDeCierre> requisitos;

  /// Lo que impide afirmar que el trabajo terminó.
  List<RequisitoDeCierre> get bloqueantes =>
      requisitos.where((r) => r.bloquea).toList();

  bool get puedeCerrar => bloqueantes.isEmpty;

  /// Lo hecho pero sin llegar al servidor todavía.
  bool get hayPendienteDeSubir =>
      requisitos.any((r) => r.estado == EstadoDeRequisito.sinSubir);

  bool get hayConflictos =>
      requisitos.any((r) => r.estado == EstadoDeRequisito.conConflicto);

  /// Arma el checklist con lo que la orden pide y lo que ya se hizo.
  ///
  /// [camposObligatoriosSinLlenar] y [requisitosDeFoto] vienen del esquema del
  /// tipo de trabajo: son lo que Dexter declaró obligatorio.
  ///
  /// [exigeFirma] también llega del esquema. Cuando una empresa no pide firma,
  /// no se inventa un requisito que nadie declaró.
  static CierreDeOrden evaluar({
    required List<String> camposObligatoriosSinLlenar,
    required List<dynamic> requisitosDeFoto,
    required List<Map<String, dynamic>> fotosCapturadas,
    required List<Map<String, dynamic>> materialesRegistrados,
    required bool exigeFirma,
    required bool hayFirma,
    bool firmaSinSubir = false,
  }) {
    final lineas = <RequisitoDeCierre>[];

    // 1. El formulario.
    if (camposObligatoriosSinLlenar.isEmpty) {
      lineas.add(const RequisitoDeCierre(
        titulo: 'Datos del trabajo',
        estado: EstadoDeRequisito.completo,
      ));
    } else {
      lineas.add(RequisitoDeCierre(
        titulo: 'Datos del trabajo',
        estado: EstadoDeRequisito.pendiente,
        detalle: camposObligatoriosSinLlenar.length == 1
            ? 'Falta: ${camposObligatoriosSinLlenar.first}'
            : 'Faltan ${camposObligatoriosSinLlenar.length} campos',
      ));
    }

    // 2. Las fotografías. Las opcionales se muestran y no bloquean: eso lo
    //    decide `obligatorio`, que viene del servidor.
    final pendientes = <dynamic>[
      for (final req in requisitosDeFoto)
        if (!_tieneFoto(req, fotosCapturadas)) req,
    ];
    final obligatoriasPendientes = pendientes
        .where((req) => (req as Map)['obligatorio'] == true)
        .length;

    if (requisitosDeFoto.isEmpty) {
      lineas.add(const RequisitoDeCierre(
        titulo: 'Evidencia fotográfica',
        estado: EstadoDeRequisito.completo,
        detalle: 'Este trabajo no pide fotos',
      ));
    } else if (obligatoriasPendientes > 0) {
      lineas.add(RequisitoDeCierre(
        titulo: 'Evidencia fotográfica',
        estado: EstadoDeRequisito.pendiente,
        detalle: obligatoriasPendientes == 1
            ? 'Falta 1 foto obligatoria'
            : 'Faltan $obligatoriasPendientes fotos obligatorias',
      ));
    } else if (pendientes.isNotEmpty) {
      lineas.add(RequisitoDeCierre(
        titulo: 'Evidencia fotográfica',
        estado: EstadoDeRequisito.opcional,
        detalle: '${pendientes.length} opcional(es) sin tomar',
      ));
    } else {
      lineas.add(RequisitoDeCierre(
        titulo: 'Evidencia fotográfica',
        estado: EstadoDeRequisito.completo,
        detalle: '${fotosCapturadas.length} de ${requisitosDeFoto.length}',
      ));
    }

    // 3. Los materiales.
    //
    //    No bloquean nunca, ni siquiera estando vacíos: hay trabajos que no
    //    gastan nada —una revisión, una medición— y exigir material ahí
    //    obligaría a inventar un consumo para poder cerrar. Lo que sí se
    //    muestra es el estado, porque un descuadre tiene que verse.
    lineas.add(_lineaDeMateriales(materialesRegistrados));

    // 4. La firma, si esta empresa la pide.
    if (exigeFirma) {
      if (!hayFirma) {
        lineas.add(const RequisitoDeCierre(
          titulo: 'Firma del cliente',
          estado: EstadoDeRequisito.pendiente,
          detalle: 'Falta la conformidad',
        ));
      } else {
        lineas.add(RequisitoDeCierre(
          titulo: 'Firma del cliente',
          estado: firmaSinSubir
              ? EstadoDeRequisito.sinSubir
              : EstadoDeRequisito.completo,
          detalle: firmaSinSubir ? 'Firmada, sube al haber señal' : 'Firmada',
        ));
      }
    }

    return CierreDeOrden(lineas);
  }

  static RequisitoDeCierre _lineaDeMateriales(
    List<Map<String, dynamic>> registrados,
  ) {
    if (registrados.isEmpty) {
      return const RequisitoDeCierre(
        titulo: 'Materiales utilizados',
        estado: EstadoDeRequisito.opcional,
        detalle: 'No registraste material en este trabajo',
      );
    }

    final conConflicto = registrados.where((m) {
      final resultado = (m['resultado'] ?? '').toString();
      return resultado == 'conflicto' ||
          resultado == 'descuadre' ||
          resultado == 'rechazado';
    }).toList();

    if (conConflicto.isNotEmpty) {
      final primero = conConflicto.first;
      return RequisitoDeCierre(
        titulo: 'Materiales utilizados',
        estado: EstadoDeRequisito.conConflicto,
        detalle: (primero['motivo'] ?? 'Hay que revisarlo').toString(),
      );
    }

    final sinSubir = registrados
        .where((m) => (m['estado'] ?? '') != 'confirmado')
        .length;

    if (sinSubir > 0) {
      return RequisitoDeCierre(
        titulo: 'Materiales utilizados',
        estado: EstadoDeRequisito.sinSubir,
        detalle: sinSubir == 1
            ? '1 registro sube al haber señal'
            : '$sinSubir registros suben al haber señal',
      );
    }

    return RequisitoDeCierre(
      titulo: 'Materiales utilizados',
      estado: EstadoDeRequisito.completo,
      detalle: registrados.length == 1
          ? '1 material registrado'
          : '${registrados.length} materiales registrados',
    );
  }

  static bool _tieneFoto(dynamic requisito, List<Map<String, dynamic>> fotos) {
    final Object? id = (requisito as Map)['id'];
    if (id == null) return false;
    return fotos.any((f) => f['requisito_id'] == id);
  }
}
