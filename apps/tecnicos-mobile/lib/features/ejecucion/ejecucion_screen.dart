import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:uuid/uuid.dart';
import '../../demo/field_mock_data.dart';
import '../../core/storage/evidencia_storage_service.dart';
import '../../core/storage/local_database.dart';
import '../detalle_orden/pasos_orden.dart';
import '../trabajo/estado_trabajo.dart';
import 'campo_del_formulario.dart';
import 'cierre_de_orden.dart';
import 'datos_de_ejecucion.dart';
import 'widgets/consumo_de_material.dart';
import 'widgets/firma_del_cliente.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/widgets/contenido_centrado.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/offline_saved_banner.dart';
import '../../core/widgets/sync_badge.dart';
import 'progreso_evidencias.dart';
import 'widgets/bloque_academia.dart';
import 'widgets/formulario_de_campo.dart';

/// El trabajo, ejecutándose: el formulario de campo y la evidencia.
///
/// El aspecto es el del diseño de Stitch; las preguntas siguen siendo las que
/// manda el backend con la orden (`formulario_campos_json`), y cada respuesta
/// se guarda en SQLite en el momento, sin esperar a tener señal.
class EjecucionScreen extends StatefulWidget {
  final String ordenId;

  /// Enciende lo que el diseño muestra y todavía no existe: la sugerencia de
  /// reemplazo, el medidor por Bluetooth y las cápsulas de Academia.
  final bool mostrarDatosFuturos;

  /// De dónde salen los datos. Nula en la aplicación: se usa la base del
  /// teléfono. En una prueba o una captura se pasa otra, y el dibujo es el
  /// mismo — que es justamente lo que se quiere comparar.
  final FuenteDeEjecucion? fuente;

  /// El estado de la cola, si ya se conoce. Nulo: el chip lo consulta solo.
  final SyncSummary? resumenDeSync;

  const EjecucionScreen({
    super.key,
    required this.ordenId,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
    this.fuente,
    this.resumenDeSync,
  });

  @override
  State<EjecucionScreen> createState() => _EjecucionScreenState();
}

class _EjecucionScreenState extends State<EjecucionScreen> {
  late final FuenteDeEjecucion _fuente = widget.fuente ?? FuenteLocalDeEjecucion();

  /// Las hojas modales —consumo de material, firma— hablan con la base por su
  /// cuenta. No pasan por la fuente porque sólo existen cuando alguien toca un
  /// botón: nunca se abren solas al dibujar, así que no impiden montar la
  /// pantalla en una prueba.
  late final LocalDatabase _baseParaHojas = LocalDatabase();
  final ImagePicker _picker = ImagePicker();

  Map<String, dynamic>? _orden;
  String? _orgId;
  String? _profileId;

  /// Lo que se registro como usado en ESTA orden.
  ///
  /// Se lee de la cola y no de un contador propio: la cola es la que sube, y
  /// un numero aparte se desincronizaria en cuanto algo se reintente.
  List<Map<String, dynamic>> _materialesUsados = <Map<String, dynamic>>[];
  bool _isLoading = true;

  /// La carga terminó y no había nada que mostrar.
  bool _noSePudoCargar = false;
  bool _showSavedIndicator = false;
  Timer? _savedIndicatorTimer;

  /// El botón "Borrador" no guarda nada nuevo —cada respuesta ya se escribió
  /// en SQLite al tocarla—: confirma que lo escrito está a salvo.
  bool _borradorConfirmado = false;
  Timer? _borradorTimer;

  List<dynamic> _campos = [];
  List<dynamic> _evidenciasRequisitos = [];
  Map<String, dynamic> _valoresFormulario = {};
  List<Map<String, dynamic>> _evidenciasCapturadas = [];

  final Map<String, TextEditingController> _controllers = {};

  @override
  void initState() {
    super.initState();
    _loadOrdenData();
  }

  @override
  void dispose() {
    _savedIndicatorTimer?.cancel();
    _borradorTimer?.cancel();
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  void _triggerSavedBanner() {
    setState(() {
      _showSavedIndicator = true;
    });
    _savedIndicatorTimer?.cancel();
    _savedIndicatorTimer = Timer(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() {
          _showSavedIndicator = false;
        });
      }
    });
  }

  Future<void> _loadOrdenData() async {
    final DatosDeEjecucion? datos = await _fuente.cargar(widget.ordenId);
    if (datos == null) {
      // No hay sesión, o la orden todavía no bajó al teléfono. Antes esto
      // devolvía en silencio y la pantalla quedaba en blanco para siempre:
      // sin decir qué pasó y sin forma de salir.
      if (mounted) {
        setState(() {
          _isLoading = false;
          _noSePudoCargar = true;
        });
      }
      return;
    }

    _orgId = datos.orgId;
    _profileId = datos.profileId;
    _campos = datos.campos;
    _evidenciasRequisitos = datos.requisitosDeEvidencia;
    _valoresFormulario = Map<String, dynamic>.from(datos.valores);
    _materialesUsados = datos.materialesUsados;
    _evidenciasCapturadas = datos.evidenciasCapturadas;

    // Un controlador por campo, con lo que ya estaba respondido.
    //
    // El id sale del modelo normalizado, no de leer el JSON a mano: era la
    // quinta interpretacion del mismo esquema y la unica que quedaba.
    for (final CampoDelFormulario campo
        in CampoDelFormulario.normalizar(_campos, _valoresFormulario)) {
      _controllers[campo.id] =
          TextEditingController(text: campo.valor?.toString() ?? '');
    }

    if (mounted) {
      setState(() {
        _orden = datos.orden;
        _isLoading = false;
      });
    }
  }

  Future<void> _onFieldChanged(String clave, dynamic valor) async {
    if (_orgId == null || _profileId == null) return;

    _valoresFormulario[clave] = valor;

    // Persistencia atómica inmediata en SQLite
    await _fuente.guardarCampo(
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
      clave: clave,
      valor: valor,
    );

    _fuente.refrescarResumen();
    _triggerSavedBanner();
  }

  Future<void> _tomarFoto(String requisitoId) async {
    if (_orgId == null || _profileId == null) return;

    try {
      final XFile? foto = await _picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 85,
        maxWidth: 1920,
      );

      if (foto == null) return;

      // El instante en que la persona apreto el obturador -- no el de encolar,
      // que llega despues de copiar el archivo y calcular su sha256.
      final DateTime capturadaEn = DateTime.now();

      final tempFile = File(foto.path);
      // El id se genera ANTES de copiar el archivo porque el archivo se llama
      // como él: si la fila se perdiera, la foto sigue diciendo cual es su
      // evidencia, de quien es y de que orden.
      final evId = const Uuid().v4();
      // Persistir inmediatamente en almacenamiento seguro y durable privado
      final persistentFile = await EvidenciaStorageService.persistirArchivoCaptura(
        tempFile,
        nombreOriginal: foto.name,
        orgId: _orgId!,
        profileId: _profileId!,
        ordenId: widget.ordenId,
        evidenciaId: evId,
      );
      final sha = await SyncQueueService.calcularSha256(persistentFile);
      final size = await persistentFile.length();
      final registroKey = const Uuid().v4();
      final confirmacionKey = const Uuid().v4();

      await _fuente.encolarEvidencia(
        id: evId,
        orgId: _orgId!,
        profileId: _profileId!,
        ordenId: widget.ordenId,
        requisitoId: requisitoId,
        archivoPath: persistentFile.path,
        sha256: sha,
        tamanoBytes: size,
        mimeType: 'image/jpeg',
        registroIdempotencyKey: registroKey,
        confirmacionIdempotencyKey: confirmacionKey,
        capturadaEn: capturadaEn,
      );

      _evidenciasCapturadas = await _fuente.evidenciasDe(
        orgId: _orgId!,
        profileId: _profileId!,
        ordenId: widget.ordenId,
      );

      _triggerSavedBanner();

      // Disparar sincronización oportunista de fondo
      _fuente.procesarCola();

      if (mounted) setState(() {});
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error al capturar foto: $e')),
        );
      }
    }
  }

  Future<void> _completarOrden() async {
    if (_orden == null || _orgId == null || _profileId == null) return;

    // El botón le pregunta AL MISMO veredicto que dibuja el checklist.
    //
    // Antes tenía su propia validación: recorría el esquema por su cuenta y
    // sólo miraba si el campo estaba vacío. Con una medición fuera del rango
    // que el esquema declara —un -45 dBm donde se piden entre -30 y -5— el
    // checklist objetaba y el botón dejaba cerrar igual. La orden se firmaba
    // con un número imposible, y eso nadie lo vuelve a mirar.
    //
    // Era la cuarta lectura independiente del mismo esquema. Esta es la que
    // decidía de verdad.
    final CierreDeOrden veredicto = _cierre;
    if (!veredicto.puedeCerrar) {
      final RequisitoDeCierre primero = veredicto.bloqueantes.first;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: AppTheme.errorRed,
          content: Text(
            primero.detalle.isEmpty
                ? '${primero.titulo}: falta completarlo.'
                : '${primero.titulo}: ${primero.detalle}',
          ),
        ),
      );
      return;
    }

    // Todo satisfecho: transicionar localmente a completada_pendiente_sync.
    final revisionBase = _orden!['revision'] as int? ?? 0;
    final idempotencyKey = const Uuid().v4();

    await _fuente.transicionar(
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
      nuevoEstadoLocal: 'completada_pendiente_sync',
      tipoAccion: 'completar',
      revisionBase: revisionBase,
      idempotencyKey: idempotencyKey,
    );

    // 4. Intentar sincronización en segundo plano
    _fuente.procesarCola();

    if (mounted) {
      await showDialog(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          icon: const Icon(Icons.check_circle, color: AppTheme.successGreen, size: 48),
          title: const Text('¡Trabajo Finalizado con Éxito!'),
          content: const Text(
            'La orden ha quedado guardada de forma segura en este dispositivo. Si no hay conexión, se enviará al servidor automáticamente al reconectar.',
          ),
          actions: [
            ElevatedButton(
              onPressed: () {
                Navigator.of(ctx).pop();
                Navigator.of(context).pop();
              },
              child: const Text('ENTENDIDO'),
            ),
          ],
        ),
      );
    }
  }

  void _confirmarBorrador() {
    // No escribe: solo confirma. Cada respuesta ya se guardó al tocarla.
    _triggerSavedBanner();
    setState(() => _borradorConfirmado = true);
    _borradorTimer?.cancel();
    _borradorTimer = Timer(const Duration(milliseconds: 1500), () {
      if (mounted) setState(() => _borradorConfirmado = false);
    });
  }

  /// Lo registrado en esta orden, de la cola local.
  Future<List<Map<String, dynamic>>> _materialesDeEstaOrden() async {
    if (_orgId == null || _profileId == null) return <Map<String, dynamic>>[];
    final todos = await _fuente.materialesDe(
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
    );
    return todos;
  }

  Future<void> _abrirConsumoDeMaterial() async {
    if (_orgId == null || _profileId == null) return;
    final registrado = await ConsumoDeMaterial.abrir(
      context,
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
      ordenNumero: _numeroDeLaOrden,
      baseLocal: _baseParaHojas,
    );
    if (registrado != true || !mounted) return;
    final usados = await _materialesDeEstaOrden();
    if (!mounted) return;
    setState(() => _materialesUsados = usados);
  }

  /// El numero de la orden, si se pudo leer. Nunca se inventa uno.
  int? get _numeroDeLaOrden {
    final valor = _orden?['numero'];
    if (valor is int) return valor;
    return int.tryParse(valor?.toString() ?? '');
  }

  /// El paso de materiales.
  ///
  /// Va junto al formulario y las evidencias porque es parte del mismo gesto:
  /// lo que se hizo, con que se hizo y como quedo. Sacarlo a otra pantalla
  /// convertiria "anotar dos conectores" en un viaje de ida y vuelta que nadie
  /// hace con las manos en la caja terminal.
  Widget _bloqueDeMateriales() {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
        border: Border.all(color: AppColors.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text('Materiales utilizados',
                        style: AppTypography.tituloChico),
                    Text(
                      'Se descuenta de tu kit y sube cuando haya señal',
                      style: AppTypography.cuerpoChico,
                    ),
                  ],
                ),
              ),
              Text(
                '${_materialesUsados.length}',
                style: AppTypography.dato.copyWith(
                  color: AppColors.onSurfaceVariant,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (_materialesUsados.isEmpty)
            Text(
              'Todavía no registraste material en este trabajo.',
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
            )
          else
            for (final m in _materialesUsados)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: <Widget>[
                    Icon(
                      (m['estado'] ?? '') == 'confirmado'
                          ? Icons.cloud_done_outlined
                          : Icons.schedule,
                      size: 16,
                      color: AppColors.onSurfaceVariant,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '${m['material_nombre'] ?? m['material_codigo']} '
                        'x${m['cantidad']}'
                        '${(m['serie'] as String?)?.isNotEmpty == true ? ' · ${m['serie']}' : ''}',
                        style: AppTypography.cuerpo,
                      ),
                    ),
                  ],
                ),
              ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            height: 44,
            child: OutlinedButton.icon(
              onPressed: _abrirConsumoDeMaterial,
              icon: const Icon(Icons.add, size: 18),
              label: const Text('Agregar material'),
            ),
          ),
        ],
      ),
    );
  }

  /// El requisito de firma que declara este tipo de trabajo, si lo declara.
  ///
  /// Se reconoce por su tipo en el esquema, no por su texto: buscar la palabra
  /// "firma" en la descripcion funcionaria hasta que una empresa escriba
  /// "conformidad del abonado" y dejaria de andar sin que nadie lo note.
  Map<String, dynamic>? get _requisitoDeFirma {
    for (final dynamic req in _evidenciasRequisitos) {
      if (req is Map && (req['tipo'] ?? '').toString() == 'firma') {
        return Map<String, dynamic>.from(req);
      }
    }
    return null;
  }

  bool get _exigeFirma => _requisitoDeFirma != null;

  bool get _hayFirma {
    final requisito = _requisitoDeFirma;
    if (requisito == null) return false;
    return _evidenciasCapturadas
        .any((e) => e['requisito_id'] == requisito['id']);
  }

  bool get _firmaSinSubir {
    final requisito = _requisitoDeFirma;
    if (requisito == null) return false;
    return _evidenciasCapturadas.any((e) =>
        e['requisito_id'] == requisito['id'] &&
        (e['subida_estado'] ?? '') != 'confirmada');
  }

  /// Los campos del formulario, interpretados una sola vez.
  ///
  /// La misma lista que se le pasa al widget del formulario: si el checklist
  /// de cierre leyera el esquema por su cuenta volveriamos a tener dos
  /// lecturas que se desincronizan. Ya paso: el formulario pintaba el
  /// asterisco rojo y el cierre no exigia el campo.
  List<CampoDelFormulario> get _camposNormalizados =>
      CampoDelFormulario.normalizar(_campos, _valoresFormulario);

  /// Lo que impide cerrar por el lado de los datos: obligatorios sin
  /// responder, y tambien valores que no sirven.
  List<String> get _camposObligatoriosSinLlenar => <String>[
        for (final CampoDelFormulario campo in _camposNormalizados)
          if (campo.bloqueaCierre) campo.titulo,
      ];

  CierreDeOrden get _cierre => CierreDeOrden.evaluar(
        camposObligatoriosSinLlenar: _camposObligatoriosSinLlenar,
        requisitosDeFoto: <dynamic>[
          for (final dynamic r in _evidenciasRequisitos)
            if (!(r is Map && (r['tipo'] ?? '').toString() == 'firma')) r,
        ],
        fotosCapturadas: _evidenciasCapturadas,
        materialesRegistrados: _materialesUsados,
        exigeFirma: _exigeFirma,
        hayFirma: _hayFirma,
        firmaSinSubir: _firmaSinSubir,
      );

  Future<void> _abrirFirma() async {
    final requisito = _requisitoDeFirma;
    if (requisito == null || _orgId == null || _profileId == null) return;

    final firmado = await FirmaDelCliente.abrir(
      context,
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
      requisitoId: (requisito['id'] ?? '').toString(),
      resumenDelTrabajo: _resumenParaElCliente,
      materialesInstalados: <String>[
        for (final m in _materialesUsados)
          '${m['material_nombre'] ?? m['material_codigo']} x${m['cantidad']}'
          '${(m['serie'] as String?)?.isNotEmpty == true ? ' · serie ${m['serie']}' : ''}',
      ],
      baseLocal: _baseParaHojas,
    );
    if (firmado != true || !mounted) return;

    final evidencias = await _fuente.evidenciasDe(
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
    );
    if (!mounted) return;
    setState(() => _evidenciasCapturadas = evidencias);
  }

  /// Lo que el cliente esta aceptando, en una linea.
  String get _resumenParaElCliente {
    final tipo = (_orden?['tipo_nombre'] ?? 'Trabajo').toString();
    final numero = _numeroDeLaOrden;
    return numero == null ? tipo : '$tipo · OT #$numero';
  }

  /// El checklist de cierre.
  ///
  /// Siempre las mismas lineas, en el mismo orden: uno que cambia obliga a
  /// leerlo entero cada vez, y esto se mira parado en una vereda.
  Widget _checklistDeCierre() {
    final cierre = _cierre;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
        border: Border.all(color: AppColors.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Antes de cerrar', style: AppTypography.tituloChico),
          const SizedBox(height: 10),
          for (final requisito in cierre.requisitos)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(_iconoDe(requisito.estado),
                      size: 18, color: _colorDe(requisito.estado)),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(requisito.titulo, style: AppTypography.cuerpo),
                        if (requisito.detalle.isNotEmpty)
                          Text(
                            requisito.detalle,
                            style: AppTypography.cuerpoChico.copyWith(
                              color: _colorDe(requisito.estado),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          if (_exigeFirma && !_hayFirma) ...<Widget>[
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              height: 44,
              child: OutlinedButton.icon(
                onPressed: _abrirFirma,
                icon: const Icon(Icons.draw_outlined, size: 18),
                label: const Text('Tomar la firma del cliente'),
              ),
            ),
          ],
          if (cierre.hayPendienteDeSubir) ...<Widget>[
            const SizedBox(height: 10),
            Text(
              'Hay trabajo hecho que todavía no llegó al servidor. Sube solo '
              'cuando haya señal; no hace falta esperar acá.',
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
            ),
          ],
        ],
      ),
    );
  }

  IconData _iconoDe(EstadoDeRequisito estado) => switch (estado) {
        EstadoDeRequisito.completo => Icons.check_circle,
        EstadoDeRequisito.pendiente => Icons.radio_button_unchecked,
        EstadoDeRequisito.opcional => Icons.remove_circle_outline,
        EstadoDeRequisito.sinSubir => Icons.schedule,
        EstadoDeRequisito.conConflicto => Icons.error_outline,
      };

  Color _colorDe(EstadoDeRequisito estado) => switch (estado) {
        EstadoDeRequisito.completo => AppColors.exito,
        EstadoDeRequisito.pendiente => AppColors.error,
        EstadoDeRequisito.opcional => AppColors.onSurfaceVariant,
        EstadoDeRequisito.sinSubir => AppColors.onSurfaceVariant,
        EstadoDeRequisito.conConflicto => AppColors.error,
      };

  @override
  Widget build(BuildContext context) {
    if (_noSePudoCargar) {
      return Scaffold(
        backgroundColor: AppColors.surface,
        appBar: AppBar(title: const Text('Ejecución')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const Icon(Icons.cloud_off,
                    size: 40, color: AppColors.onSurfaceVariant),
                const SizedBox(height: AppSpacing.md),
                Text(
                  'No pudimos abrir este trabajo',
                  style: AppTypography.tituloChico,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'La orden todavía no está en este teléfono. Volvé a la '
                  'lista y sincronizá cuando tengas señal.',
                  style: AppTypography.cuerpo,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: AppSpacing.lg),
                // Una salida. Sin esto la unica forma de irse es el gesto de
                // volver del sistema, y en una pantalla en blanco nadie sabe
                // si la aplicacion se colgo.
                FilledButton(
                  onPressed: () => Navigator.of(context).maybePop(),
                  child: const Text('Volver'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    if (_isLoading) {
      // Un fondo quieto, no un indicador que gira. Es la misma decision que
      // ya tomaron Inicio y Materiales: esto lee SQLite y son milisegundos,
      // asi que el spinner solo hace parpadear la pantalla. Ademas una
      // animacion perpetua deja el arbol sin reposo y cuelga cualquier
      // prueba que espere a que las animaciones terminen -- que es
      // exactamente lo que pasaba al intentar probar esta pantalla.
      return const Scaffold(
        backgroundColor: AppColors.surface,
        body: SizedBox.expand(),
      );
    }

    final numero = _orden?['numero'] ?? '---';

    return Scaffold(
      backgroundColor: AppColors.surfaceDim,
      appBar: AppBar(
        // Sin "Ejecución": a 390 px, con el chip de la cola al lado, el
        // titulo se cortaba en "Ejecución OT #48..." y se perdia el numero,
        // que es lo unico que identifica el trabajo. La pantalla ya dice que
        // es la ejecucion en su primer bloque.
        title: Text('OT #$numero'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: AppSpacing.sm),
            child: SyncBadge(resumenFijo: widget.resumenDeSync),
          ),
        ],
      ),
      body: ContenidoCentrado(
        child: Column(
        children: [
          OfflineSavedBanner(visible: _showSavedIndicator),
          _paraQuienYEnQuePaso(),
          _franjaDelFormulario(),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.margen,
                AppSpacing.lg,
                AppSpacing.margen,
                AppSpacing.lg,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  FormularioDeCampo(
                    // Una sola lectura del esquema para toda la pantalla: la
                    // misma que usa el checklist de cierre.
                    campos: _camposNormalizados,
                    valores: _valoresFormulario,
                    controladores: _controllers,
                    alCambiar: _onFieldChanged,
                    mostrarDatosFuturos: widget.mostrarDatosFuturos,
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  _bloqueDeMateriales(),
                  _evidencias(),
                  _checklistDeCierre(),
                  if (widget.mostrarDatosFuturos) ...[
                    const SizedBox(height: AppSpacing.lg),
                    const BloqueAcademia(),
                  ],
                ],
              ),
            ),
          ),
          _barraDeAcciones(),
        ],
        ),
      ),
    );
  }

  /// Cuántos requisitos de foto ya tienen su captura.
  int get _fotosCapturadas => fotosCapturadas(
        requisitos: _evidenciasRequisitos,
        capturadas: _evidenciasCapturadas,
      );

  /// Qué formulario se está respondiendo. La versión del esquema viene con la
  /// orden: si el backend cambia las preguntas, esto cambia con ellas.
  /// Para quién es el trabajo y en qué paso va.
  ///
  /// Esta pantalla es larga y se abre desde una lista: sin esta línea, a los
  /// tres bloques de scroll ya no se sabe de qué orden se trata. El número
  /// solo no alcanza — nadie recuerda a qué cliente corresponde el 4832.
  ///
  /// Los dos datos ya existen: el cliente viene en la orden y el paso lo
  /// calcula `LecturaDePasos`, la misma que dibuja la barra del detalle. No
  /// se agrega ninguna fuente nueva.
  Widget _paraQuienYEnQuePaso() {
    final String cliente = (_orden?['cliente_nombre'] ?? '').toString();
    final LecturaDePasos pasos =
        LecturaDePasos.de(EstadoTrabajo.desde(_orden?['estado']?.toString()));
    if (cliente.isEmpty) return const SizedBox.shrink();

    return Container(
      width: double.infinity,
      color: AppColors.surfaceContainerLowest,
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.margen,
        AppSpacing.sm,
        AppSpacing.margen,
        AppSpacing.sm,
      ),
      child: Row(
        children: <Widget>[
          const Icon(Icons.person_outline,
              size: 16, color: AppColors.onSurfaceVariant),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              cliente,
              style: AppTypography.etiquetaGrande
                  .copyWith(color: AppColors.onSurface),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: const BoxDecoration(
              color: AppColors.surfaceContainer,
              borderRadius: AppRadius.brChico,
            ),
            child: Text(
              'Paso ${pasos.pasoActual + 1} de 5',
              style: AppTypography.etiquetaChica,
            ),
          ),
        ],
      ),
    );
  }

  Widget _franjaDelFormulario() {
    final int version = _orden?['schema_version'] as int? ?? 0;
    final int campos = _campos.length;

    return Container(
      width: double.infinity,
      color: AppColors.surfaceContainerLow,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.margen,
        vertical: 6,
      ),
      child: Row(
        children: [
          const Icon(Icons.save, size: 13, color: AppColors.exitoTexto),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              'Se guarda en este equipo',
              style: AppTypography.etiquetaChica,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          // La version del formulario no se recorta: si se corta por la mitad
          // deja de servir para lo unico que sirve, que es saber contra que
          // esquema se esta trabajando.
          Text(
            version == 0
                ? '$campos campos'
                : 'v$version · $campos campos',
            style: AppTypography.datoChico.copyWith(
              color: AppColors.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  /// La evidencia fotográfica que pide el tipo de trabajo. Igual que el
  /// formulario, la lista viene del backend: acá solo se dibuja y se captura.
  Widget _evidencias() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Evidencia Fotográfica', style: AppTypography.tituloChico),
                    Text(
                      'Queda guardada en el equipo y se envía sola al recuperar señal',
                      style: AppTypography.cuerpoChico,
                    ),
                  ],
                ),
              ),
              Text(
                '$_fotosCapturadas/${_evidenciasRequisitos.length}',
                style: AppTypography.dato.copyWith(
                  color: _fotosCapturadas == _evidenciasRequisitos.length
                      ? AppColors.exitoTexto
                      : AppColors.primary,
                ),
              ),
              const SizedBox(width: 6),
              const Icon(Icons.photo_camera, size: 20, color: AppColors.outline),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          if (_evidenciasRequisitos.isEmpty)
            Text(
              'Este tipo de trabajo no exige fotografías.',
              style: AppTypography.cuerpoChico,
            )
          else
            for (var i = 0; i < _evidenciasRequisitos.length; i++) ...[
              if (i > 0) const SizedBox(height: AppSpacing.md),
              _buildEvidenciaRequisito(
                Map<String, dynamic>.from(_evidenciasRequisitos[i] as Map),
              ),
            ],
        ],
      ),
    );
  }

  /// La barra fija del diseño: el borrador a la izquierda, el cierre a la
  /// derecha. El diseño dice "Registrar Materiales"; ese módulo todavía no
  /// existe, así que el botón hace lo que la aplicación sí sabe hacer: cerrar
  /// la orden con lo registrado.
  Widget _barraDeAcciones() {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        boxShadow: AppTheme.sombraNivel2,
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.margen,
            vertical: AppSpacing.md,
          ),
          child: Row(
            children: [
              Material(
                color: AppColors.surfaceContainer,
                borderRadius: AppRadius.brTarjeta,
                child: InkWell(
                  borderRadius: AppRadius.brTarjeta,
                  onTap: _confirmarBorrador,
                  child: Container(
                    height: AppSpacing.objetivoTactilAmplio,
                    padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
                    alignment: Alignment.center,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          _borradorConfirmado ? Icons.check : Icons.save,
                          size: 18,
                          color: AppColors.onSurface,
                        ),
                        const SizedBox(width: AppSpacing.xs),
                        Text(
                          _borradorConfirmado ? 'Guardado' : 'Borrador',
                          style: AppTypography.etiqueta
                              .copyWith(color: AppColors.onSurface),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Material(
                  color: AppColors.primary,
                  borderRadius: AppRadius.brTarjeta,
                  child: InkWell(
                    borderRadius: AppRadius.brTarjeta,
                    onTap: _completarOrden,
                    child: Container(
                      height: AppSpacing.objetivoTactilAmplio,
                      alignment: Alignment.center,
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            'Finalizar orden',
                            style: AppTypography.etiquetaGrande
                                .copyWith(color: AppColors.onPrimary),
                          ),
                          const SizedBox(width: AppSpacing.sm),
                          const Icon(
                            Icons.arrow_forward,
                            size: 20,
                            color: AppColors.onPrimary,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEvidenciaRequisito(Map<String, dynamic> req) {
    final reqId = req['id'] as String;
    final descripcion = (req['descripcion'] ?? req['titulo'] ?? reqId) as String;
    final obligatorio = req['obligatorio'] == true;
    final instrucciones = req['instrucciones'] as String?;

    final evidencia = _evidenciasCapturadas.firstWhere(
      (e) => e['requisito_id'] == reqId,
      orElse: () => {},
    );
    final hasFoto = evidencia.isNotEmpty && evidencia['archivo_path'] != null;
    final filePath = hasFoto ? evidencia['archivo_path'] as String : null;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
        border: !hasFoto && obligatorio
            ? Border.all(color: AppColors.onErrorContainer.withValues(alpha: 0.4))
            : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: hasFoto
                      ? AppColors.exitoFondo
                      : AppColors.surfaceContainer,
                  borderRadius: AppRadius.brCampo,
                ),
                child: Icon(
                  hasFoto ? Icons.check_circle : Icons.camera_alt_outlined,
                  size: 18,
                  color: hasFoto ? AppColors.exito : AppColors.secondary,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  '$descripcion${obligatorio ? ' *' : ''}',
                  style: AppTypography.etiqueta.copyWith(color: AppColors.onSurface),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: hasFoto
                      ? AppColors.exitoFondo
                      : (obligatorio
                          ? AppColors.errorContainer
                          : AppColors.surfaceContainer),
                  borderRadius: AppRadius.brChico,
                ),
                child: Text(
                  hasFoto ? 'CAPTURADA' : 'PENDIENTE',
                  style: AppTypography.etiquetaChica.copyWith(
                    color: hasFoto
                        ? AppColors.exitoTexto
                        : (obligatorio
                            ? AppColors.onErrorContainer
                            : AppColors.onSurfaceVariant),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          if (instrucciones != null && instrucciones.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(instrucciones, style: AppTypography.etiquetaChica),
          ],
          const SizedBox(height: AppSpacing.sm),
          if (hasFoto && filePath != null) ...[
            ClipRRect(
              borderRadius: AppRadius.brTarjeta,
              child: Image.file(
                File(filePath),
                height: 140,
                width: double.infinity,
                fit: BoxFit.cover,
                errorBuilder: (context, error, stackTrace) =>
                    const Text('No se puede cargar la vista previa'),
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
          ],
          SizedBox(
            height: AppSpacing.objetivoTactil,
            child: OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.primary,
                side: const BorderSide(color: AppColors.outlineVariant),
                shape: const RoundedRectangleBorder(
                  borderRadius: AppRadius.brTarjeta,
                ),
              ),
              icon: Icon(hasFoto ? Icons.replay : Icons.camera_alt, size: 18),
              label: Text(hasFoto ? 'VOLVER A TOMAR' : 'TOMAR FOTOGRAFÍA'),
              onPressed: () => _tomarFoto(reqId),
            ),
          ),
        ],
      ),
    );
  }
}
