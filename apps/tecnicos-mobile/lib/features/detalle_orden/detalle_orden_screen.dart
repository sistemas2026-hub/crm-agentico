import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/estado/ordenes_jornada.dart';
import '../../demo/field_mock_data.dart';
import '../../demo/kit_mock_data.dart';
import '../materiales/material_en_custodia.dart';
import '../../core/sync/sync_presentacion.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_card.dart';
import '../../core/widgets/dexter_empty_state.dart';
import '../../core/widgets/contenido_centrado.dart';
import '../../core/widgets/dexter_sync_badge.dart';
import '../ejecucion/ejecucion_screen.dart';
import '../trabajo/estado_trabajo.dart';
import '../trabajo/trabajo_vista.dart';
import 'acciones_orden.dart';
import 'pasos_orden.dart';

/// La orden, abierta.
///
/// Sirve para entender qué hay que hacer y para avanzar el estado. El
/// formulario y las fotos siguen viviendo en la pantalla de ejecución.
///
/// No carga órdenes por su cuenta: lee la que le toca de [OrdenesJornada], la
/// misma lista que muestran Inicio y Trabajo, y la refresca después de cada
/// transición para que las tres queden iguales.
/// Los valores de ejemplo de un trabajo.
///
/// Se piden acá y no dentro de `TrabajoVista`: un modelo que trae adentro un
/// dato inventado se lo entrega a cualquiera que lo lea —`trabajo.futuro.zona`
/// devolvía siempre algo, hubiera zona o no— y arrastraba al núcleo a depender
/// de la demostración a través de `ordenes_jornada.dart`.
TrabajoFuturoMock _ejemploDe(TrabajoVista trabajo) =>
    FieldMockData.trabajoFuturo(trabajo.id);

class DetalleOrdenScreen extends StatefulWidget {
  const DetalleOrdenScreen({
    super.key,
    required this.ordenId,
    required this.ordenes,
    required this.acciones,
    this.resumenes,
    this.resumenInicial,
    this.abrirEjecucion,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
  });

  final String ordenId;
  final OrdenesJornada ordenes;
  final AccionesOrden acciones;

  /// Estado de la cola. Esta pantalla vive fuera del contenedor, así que se
  /// suscribe por su cuenta y se da de baja al cerrarse.
  final Stream<SyncSummary>? resumenes;
  final SyncSummary? resumenInicial;

  /// Qué hacer al tocar "Ejecutar el trabajo". Por defecto, la pantalla de
  /// ejecución que ya existe.
  final Future<void> Function(BuildContext contexto, TrabajoVista trabajo)?
  abrirEjecucion;

  final bool mostrarDatosFuturos;

  @override
  State<DetalleOrdenScreen> createState() => _DetalleOrdenScreenState();
}

/// En cuantas tandas se piden los paquetes del ping, y de que tamaño.
///
/// **El mínimo que WispHub acepta es 3**, medido el 25/09/2026: pedir 1 o 2
/// devuelve HTTP 400. Por eso los paquetes no se pueden pedir de a uno para
/// irlos mostrando -- la tanda más chica es de tres.
///
/// Y no se pide una sola de diez: esa tarda ~18 s con el técnico mirando una
/// rueda girar sin saber si el primero volvió. En tandas, los primeros caen a
/// los ~5 s. Se pagan tres llamadas en vez de una; a cambio se ve el ping
/// pasar, que es para lo que se pide.
///
/// Tiene que sumar lo mismo que TANDAS en campo/services/telemetria.py.
const List<int> _tandasDelPing = <int>[3, 3, 4];
const int _paquetesDelPing = 10;

class _DetalleOrdenScreenState extends State<DetalleOrdenScreen> {
  StreamSubscription<SyncSummary>? _suscripcionResumen;
  SyncSummary? _resumen;
  bool _trabajando = false;
  bool _pingEnCurso = false;
  ResultadoPing? _ping;

  @override
  void initState() {
    super.initState();
    _resumen = widget.resumenInicial;
    widget.ordenes.addListener(_alCambiar);
    // Normalmente se llega desde Inicio o Trabajo, con la lista ya cargada.
    // Pero si alguien abre esta pantalla antes —o la lista se vacia— hay que
    // pedirla: sin esto, la pantalla diria que la orden no existe.
    widget.ordenes.asegurarCargado();
    _suscripcionResumen = widget.resumenes?.listen((SyncSummary resumen) {
      if (mounted) setState(() => _resumen = resumen);
    }, onError: (Object _) {});
  }

  @override
  void dispose() {
    widget.ordenes.removeListener(_alCambiar);
    _suscripcionResumen?.cancel();
    super.dispose();
  }

  void _alCambiar() {
    if (mounted) setState(() {});
  }

  TrabajoVista? get _trabajo {
    for (final TrabajoVista t in widget.ordenes.trabajos) {
      if (t.id == widget.ordenId) return t;
    }
    return null;
  }

  Future<void> _ejecutarAccion(TrabajoVista trabajo, AccionOrden accion) async {
    if (_trabajando) return;

    if (accion.abreEjecucion) {
      final abrir = widget.abrirEjecucion ?? _abrirEjecucionPorDefecto;
      await abrir(context, trabajo);
      await widget.ordenes.recargar();
      return;
    }

    setState(() => _trabajando = true);
    try {
      await widget.acciones.transicionar(
        ordenId: trabajo.id,
        nuevoEstadoLocal: accion.nuevoEstadoLocal!,
        tipoAccion: accion.tipoAccion!,
        revisionBase: trabajo.revision,
      );
      // La lista compartida se relee: Inicio y Trabajo ven el estado nuevo.
      await widget.ordenes.recargar();
    } finally {
      if (mounted) setState(() => _trabajando = false);
    }
  }

  Future<void> _abrirEjecucionPorDefecto(
    BuildContext contexto,
    TrabajoVista trabajo,
  ) async {
    await Navigator.of(contexto).push(
      MaterialPageRoute<void>(
        builder: (_) => EjecucionScreen(ordenId: trabajo.id),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final trabajo = _trabajo;

    if (trabajo == null && widget.ordenes.cargando) {
      return Scaffold(
        appBar: AppBar(title: const Text('Detalle Orden')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    if (trabajo == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Detalle Orden')),
        body: const Center(
          child: DexterEmptyState(
            icono: Icons.search_off,
            titulo: 'No encontramos esta orden',
            mensaje: 'Puede haber sido reasignada. Volvé y actualizá la lista.',
            esAdvertencia: true,
          ),
        ),
      );
    }

    final lectura = LecturaDePasos.de(trabajo.estado);
    final acciones = AccionesDisponibles.para(trabajo.estado);

    return Scaffold(
      appBar: AppBar(
        title: Text(
          // Sin "Detalle": a 390 px, con la chapa de la cola al lado, el
          // titulo largo se cortaba en "Detalle Orden #…" y se perdia
          // justamente el numero, que es lo que identifica el trabajo.
          trabajo.numero == null ? 'Detalle Orden' : 'OT #${trabajo.numero}',
        ),
        actions: <Widget>[
          Padding(
            padding: const EdgeInsets.only(right: AppSpacing.sm),
            child: Center(
              child: DexterSyncBadge(
                estado: SyncPresentacion.estado(_resumen),
                detalle: SyncPresentacion.detalle(_resumen),
                onTap: widget.acciones.sincronizar,
              ),
            ),
          ),
        ],
      ),
      backgroundColor: AppColors.surfaceDim,
      body: ContenidoCentrado(
        child: Column(
        children: <Widget>[
          if (widget.mostrarDatosFuturos) _franjaDeEnlace(),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.margen,
                AppSpacing.md,
                AppSpacing.margen,
                AppSpacing.xl,
              ),
              children: <Widget>[
                if (trabajo.requiereActualizacion) _avisoActualizacion(trabajo),
                _cabeceraConPasos(trabajo, lectura),
                if (lectura.avisoExcepcion != null) ...<Widget>[
                  const SizedBox(height: AppSpacing.md),
                  _avisoExcepcion(trabajo, lectura),
                ],
                if (trabajo.estado ==
                    EstadoTrabajo.completadaSinEnviar) ...<Widget>[
                  const SizedBox(height: AppSpacing.md),
                  _avisoSinEnviar(),
                ],
                if (trabajo.correccion != null) ...<Widget>[
                  const SizedBox(height: AppSpacing.md),
                  _loQueHayQueRehacer(trabajo, trabajo.correccion!),
                ],
                const SizedBox(height: AppSpacing.md),
                _accionesRapidas(trabajo),
                const SizedBox(height: AppSpacing.md),
                _datosDelCliente(trabajo),
                // Lo que la orden SÍ trae. Antes vivía detrás de la bandera
                // de demostración junto a los datos de ejemplo, así que en
                // producción se ocultaba también lo verdadero: el ticket de
                // origen, la franja prometida y los requisitos de seguridad
                // llegan del backend y nadie los veía.
                const SizedBox(height: AppSpacing.md),
                _datosDeLaOrden(trabajo),
                const SizedBox(height: AppSpacing.md),
                _datosTecnicos(trabajo),
                // La telemetría se ve cuando la orden trae una lectura del
                // equipo, aunque no haya modo demostración: la señal óptica es
                // un dato REAL desde que el motor la consulta al armar la
                // ficha. Estaba entera detrás de la bandera, así que en
                // producción no la veía nadie — el mismo descuido que este
                // módulo ya pagó con el ticket de origen, la franja prometida
                // y los requisitos de seguridad.
                //
                // Cuando no hay lectura la tarjeta también se muestra, porque
                // decir POR QUÉ no la hay (falta el serial, el serial no está
                // en la OLT) es información, y callarla manda a buscar una
                // falla de red donde no la hay.
                if (trabajo.contextoDisponible ||
                    widget.mostrarDatosFuturos) ...<Widget>[
                  const SizedBox(height: AppSpacing.md),
                  _telemetria(trabajo),
                ],
                if (trabajo.hayEvaluacionDexter) ...<Widget>[
                  const SizedBox(height: AppSpacing.md),
                  _loQueDexterAveriguo(trabajo),
                ],
                if (trabajo.diagnosticoPrevio.isNotEmpty ||
                    widget.mostrarDatosFuturos) ...<Widget>[
                  const SizedBox(height: AppSpacing.md),
                  _triage(trabajo),
                ],
                // El protocolo se ve cuando la plantilla lo trae, aunque no
                // haya modo demostración: es un dato real del tipo de trabajo.
                if (trabajo.pasosDelProcedimiento.isNotEmpty ||
                    widget.mostrarDatosFuturos) ...<Widget>[
                  const SizedBox(height: AppSpacing.md),
                  _protocoloDeAtencion(trabajo),
                ],
                if (widget.mostrarDatosFuturos) ...<Widget>[
                  const SizedBox(height: AppSpacing.md),
                  _materialesAsociados(),
                ],
              ],
            ),
          ),
          // La barra fija del diseño: la acción principal no se pierde abajo
          // del scroll, que en esta pantalla es largo.
          Container(
            decoration: const BoxDecoration(
              color: AppColors.surfaceContainerLowest,
              boxShadow: AppTheme.sombraNivel2,
            ),
            child: SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.margen,
                  AppSpacing.md,
                  AppSpacing.margen,
                  AppSpacing.md,
                ),
                child: _acciones(trabajo, acciones),
              ),
            ),
          ),
        ],
        ),
      ),
    );
  }

  /// CAMPO-DATA-035 y CAMPO-DATA-036 · La franja del diseño: qué enlace habla
  /// con el servidor y cuándo fue el último envío bueno.
  ///
  /// La marca de tiempo todavía no existe —la cola no la guarda—, así que la
  /// franja entera vive en la demostración: un "hace 1 min" falso en la calle
  /// haría creer que lo registrado ya viajó.
  Widget _franjaDeEnlace() {
    return Container(
      width: double.infinity,
      color: AppColors.inverseSurface,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.margen,
        vertical: 6,
      ),
      child: Row(
        children: <Widget>[
          Container(
            width: 8,
            height: 8,
            decoration: const BoxDecoration(
              color: AppColors.exitoFuerte,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          // Flexibles: a 390 px los cuatro textos no entran en una fila, y un
          // Row rigido no se acomoda, desborda. El techo de ancho de la
          // aplicacion destapo esto, que antes se escondia porque las pruebas
          // renderizaban a mil pixeles.
          Flexible(
            child: Text(
              FieldMockData.enlaceDexter,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.inverseOnSurface,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          const Icon(Icons.check, size: 12, color: AppColors.exitoFuerte),
          const SizedBox(width: 2),
          Flexible(
            child: Text(
              'En dispositivo',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.exitoFuerte,
              ),
            ),
          ),
          const Spacer(),
          const Icon(Icons.cloud_done, size: 14, color: AppColors.surfaceDim),
          const SizedBox(width: 4),
          Flexible(
            child: Text(
              'Sync: ${FieldMockData.ultimaSincronizacion}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.surfaceDim,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// Cabecera del diseño: número, SLA, paso actual y la barra de pasos.
  Widget _cabeceraConPasos(TrabajoVista trabajo, LecturaDePasos lectura) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                trabajo.numero == null ? 'Orden' : '#OT-${trabajo.numero}',
                style: AppTypography.etiquetaGrande.copyWith(
                  color: AppColors.primary,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              // CAMPO-DATA-002
              if (widget.mostrarDatosFuturos)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 6,
                    vertical: 2,
                  ),
                  decoration: const BoxDecoration(
                    color: AppColors.errorContainer,
                    borderRadius: AppRadius.brChico,
                  ),
                  child: Text(
                    'SLA ${_ejemploDe(trabajo).slaRestante}h',
                    style: AppTypography.etiquetaChica.copyWith(
                      color: AppColors.onErrorContainer,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm,
                  vertical: 3,
                ),
                decoration: BoxDecoration(
                  color: AppColors.surfaceContainer,
                  borderRadius: BorderRadius.circular(AppRadius.circulo),
                ),
                child: Text(
                  lectura.pasoActual < 0
                      ? 'Sin avance'
                      : 'Paso ${lectura.pasoActual + 1} de ${PasoOrden.values.length}',
                  style: AppTypography.etiquetaChica.copyWith(
                    color: AppColors.onSurface,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            trabajo.tipoNombre,
            style: AppTypography.tituloMedio.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          // CAMPO-DATA-037 · Qué hay que hacer, en una línea.
          if (widget.mostrarDatosFuturos)
            Text(
              FieldMockData.resumenDelTrabajo,
              style: AppTypography.cuerpoChico,
            ),
          Text(trabajo.clienteNombre, style: AppTypography.cuerpoChico),
          const SizedBox(height: AppSpacing.md),
          _BarraDePasos(lectura: lectura),
        ],
      ),
    );
  }

  /// La barra de acciones rápidas del diseño. Llamar y Ruta necesitan abrir
  /// otra aplicación —todavía no autorizado—, así que se ven apagadas cuando
  /// no hay con qué: un botón que no hace nada y no lo dice es peor que uno
  /// que se ve inactivo.
  Widget _accionesRapidas(TrabajoVista trabajo) {
    return Row(
      children: <Widget>[
        Expanded(
          child: _AccionRapidaDetalle(
            icono: Icons.call,
            texto: 'Llamar',
            activa: trabajo.telefono.isNotEmpty,
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: _AccionRapidaDetalle(
            icono: Icons.navigation,
            texto: 'Ruta GPS',
            activa: trabajo.latitud != null && trabajo.longitud != null,
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: _AccionRapidaDetalle(
            icono: Icons.chat,
            texto: 'WhatsApp',
            activa: trabajo.telefono.isNotEmpty,
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: _AccionRapidaDetalle(
            icono: Icons.menu_book,
            texto: 'Guía FTTH',
            activa: widget.mostrarDatosFuturos,
            alTocar: widget.mostrarDatosFuturos ? _abrirProcedimiento : null,
          ),
        ),
      ],
    );
  }

  /// Qué pidió rehacer el supervisor.
  ///
  /// No es un dato de ejemplo: lo manda el backend en `correccion`. Hasta el
  /// 22/09/2026 esa lista vivía solo en la bitácora del servidor, así que una
  /// orden devuelta llegaba sin decir qué corregir y se averiguaba por
  /// teléfono.
  Widget _loQueHayQueRehacer(TrabajoVista trabajo, DevolucionDeValidacion c) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.errorContainer,
        borderRadius: AppRadius.brTarjeta,
        border: Border.all(
          color: AppColors.onErrorContainer.withValues(alpha: 0.35),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.assignment_return,
                  size: 18, color: AppColors.onErrorContainer),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  'Te devolvieron este trabajo',
                  style: AppTypography.etiquetaGrande.copyWith(
                    color: AppColors.onErrorContainer,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Text(
                'Vuelta ${c.vuelta}',
                style: AppTypography.datoChico.copyWith(
                  color: AppColors.onErrorContainer,
                ),
              ),
            ],
          ),
          if (c.observacion.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              '“${c.observacion}”',
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onErrorContainer,
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
          if (c.requisitos.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Text(
              c.requisitos.length == 1
                  ? 'Hay que volver a tomar esta evidencia:'
                  : 'Hay que volver a tomar estas evidencias:',
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.onErrorContainer,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            for (final String requisito in c.requisitos)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    const Icon(Icons.photo_camera,
                        size: 13, color: AppColors.onErrorContainer),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        // El título de la plantilla, que es como el técnico
                        // conoce esa foto. Si el requisito ya no existe en la
                        // plantilla se muestra su identificador: es feo, pero
                        // es cierto, y callarlo dejaría la lista incompleta.
                        trabajo.titulosDeEvidencia[requisito] ?? requisito,
                        style: AppTypography.cuerpoChico.copyWith(
                          color: AppColors.onErrorContainer,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
          if (c.devueltaEn != null) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Devuelta el ${_fechaCorta(c.devueltaEn!)}',
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.onErrorContainer,
              ),
            ),
          ],
        ],
      ),
    );
  }

  static String _fechaCorta(DateTime fecha) {
    final String dia = fecha.day.toString().padLeft(2, '0');
    final String mes = fecha.month.toString().padLeft(2, '0');
    final String hora = fecha.hour.toString().padLeft(2, '0');
    final String minuto = fecha.minute.toString().padLeft(2, '0');
    return '$dia/$mes a las $hora:$minuto';
  }

  /// CAMPO-DATA-050 · El procedimiento para la falla, como hoja de consulta.
  Future<void> _abrirProcedimiento() {
    return showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.surfaceContainerLowest,
      shape: const RoundedRectangleBorder(borderRadius: AppRadius.brHoja),
      isScrollControlled: true,
      builder: (BuildContext hoja) {
        return SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    const Icon(
                      Icons.menu_book,
                      size: 20,
                      color: AppColors.secondary,
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Text(
                        FieldMockData.procedimientoTitulo,
                        style: AppTypography.tituloChico,
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close),
                      onPressed: () => Navigator.of(hoja).pop(),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.sm),
                for (
                  int i = 0;
                  i < FieldMockData.procedimientoPasos.length;
                  i++
                )
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.xs),
                    child: Text(
                      '${i + 1}. ${FieldMockData.procedimientoPasos[i]}',
                      style: AppTypography.cuerpoChico,
                    ),
                  ),
                const SizedBox(height: AppSpacing.md),
                SizedBox(
                  width: double.infinity,
                  height: AppSpacing.objetivoTactil,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      foregroundColor: AppColors.onPrimary,
                      shape: const RoundedRectangleBorder(
                        borderRadius: AppRadius.brTarjeta,
                      ),
                    ),
                    onPressed: () => Navigator.of(hoja).pop(),
                    child: const Text('Entendido'),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  /// CAMPO-DATA-025 · Qué material tiene asignado este trabajo.
  Widget _materialesAsociados() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.inventory_2,
                size: 16,
                color: AppColors.secondary,
              ),
              const SizedBox(width: 6),
              Text(
                'Materiales & Seriales',
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.onSurface,
                ),
              ),
              const Spacer(),
              Text('Kit Asignado', style: AppTypography.etiquetaChica),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          for (final MaterialEnCustodia material in KitMockData.items.take(
            3,
          )) ...<Widget>[
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.xs),
              child: Row(
                children: <Widget>[
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          material.nombre,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: AppTypography.etiquetaChica.copyWith(
                            color: AppColors.onSurface,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        Text(
                          material.serie == null
                              ? material.detalle
                              : 'SN: ${material.serie}',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: material.serie == null
                              ? AppTypography.etiquetaChica
                              : AppTypography.datoChico.copyWith(
                                  color: AppColors.onSurfaceVariant,
                                ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Text(
                    material.unidad == 'm'
                        ? '~${material.usados} m'
                        : '${material.usados} ud',
                    style: AppTypography.dato.copyWith(
                      color: AppColors.primary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// CAMPO-DATA-049 · El protocolo del tipo de trabajo.
  ///
  /// Va aparte de la barra de estados a propósito: la barra dice dónde está la
  /// orden de verdad —lo que el técnico marcó y el backend aceptó—, y esto es
  /// el procedimiento que todavía nadie guarda.
  Widget _protocoloDeAtencion(TrabajoVista trabajo) {
    // Los pasos reales vienen con la plantilla del tipo de trabajo (el backend
    // los entrega en `tipo.pasos` desde el 22/09/2026). Solo se cae al ejemplo
    // cuando la orden todavía no los trajo.
    final bool reales = trabajo.pasosDelProcedimiento.isNotEmpty;
    final List<String> pasos =
        reales ? trabajo.pasosDelProcedimiento : FieldMockData.protocoloAtencion;
    final int pasoActual = reales ? 0 : FieldMockData.protocoloPasoActual;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.checklist, size: 16, color: AppColors.secondary),
              const SizedBox(width: 6),
              Text(
                'Protocolo de Atención',
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.onSurface,
                ),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.surfaceContainer,
                  borderRadius: BorderRadius.circular(AppRadius.circulo),
                ),
                child: Text(
                  reales
                      ? '${pasos.length} pasos'
                      : 'Paso $pasoActual de ${pasos.length}',
                  style: AppTypography.etiquetaChica.copyWith(
                    color: AppColors.onSurface,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          for (int i = 0; i < pasos.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(
                    i < pasoActual - 1
                        ? Icons.check_circle
                        : (i == pasoActual - 1
                              ? Icons.radio_button_checked
                              : Icons.radio_button_unchecked),
                    size: 14,
                    color: i < pasoActual - 1
                        ? AppColors.exito
                        : (i == pasoActual - 1
                              ? AppColors.primary
                              : AppColors.outlineVariant),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      '${i + 1}. ${pasos[i]}',
                      style: AppTypography.etiquetaChica.copyWith(
                        color: i == pasoActual - 1
                            ? AppColors.onSurface
                            : AppColors.onSurfaceVariant,
                        fontWeight: i == pasoActual - 1
                            ? FontWeight.w700
                            : FontWeight.w400,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _avisoActualizacion(TrabajoVista trabajo) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: DexterCard(
        colorAcento: AppColors.error,
        child: Row(
          children: <Widget>[
            const Icon(Icons.system_update, size: 18, color: AppColors.error),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                trabajo.versionEsquemaConocida
                    ? 'Esta orden necesita una versión más nueva de la '
                          'aplicación. Actualizala antes de trabajarla.'
                    : 'Todavía no sabemos qué versión de la aplicación necesita '
                          'esta orden: falta que baje su detalle.',
                style: AppTypography.cuerpo.copyWith(color: AppColors.error),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Lo que hay que saber antes de tocar la puerta.
  ///
  /// QUÉ ENTRA Y QUÉ NO
  /// ------------------
  /// El criterio no es "mostrar todo lo que el backend manda", sino: ¿esto
  /// cambia algo de lo que la persona va a hacer en los próximos minutos?
  ///
  /// Entra:
  ///
  /// - **De qué ticket salió.** El cliente abre la puerta diciendo "ya llamé
  ///   tres veces". Saber el ticket evita volver a preguntar lo que ya está
  ///   contestado, y es lo que permite buscar el historial.
  /// - **La franja prometida.** Es el compromiso que alguien le dio a una
  ///   persona que está esperando; llegar fuera de ella no es lo mismo que
  ///   llegar tarde a una hora estimada.
  /// - **Los requisitos de seguridad.** "Trabajo en altura" decide si el
  ///   trabajo se puede hacer hoy, con lo que hay en la camioneta. Va primero
  ///   y en rojo por eso, no por énfasis.
  ///
  /// No entra:
  ///
  /// - **La prioridad.** Sirve para decidir a cuál ir, y eso ya pasó: quien
  ///   está leyendo esta pantalla ya llegó. Vive en Inicio, que es donde
  ///   ordena.
  /// - **La zona.** Ya está dicha en la dirección; repetirla ocupa una línea
  ///   y no cambia ninguna decisión.
  ///
  /// Cada línea aparece sólo si el servidor la mandó. Una orden vieja, creada
  /// antes de que existieran estos campos, muestra menos y no inventa nada.
  Widget _datosDeLaOrden(TrabajoVista trabajo) {
    final String ventana = trabajo.ventanaTexto;
    final String origen = trabajo.origen?.etiqueta ?? '';
    final List<String> seguridad = trabajo.requisitosSeguridad;

    // El ticket del ISP cuenta para decidir si la tarjeta existe. Sin esto,
    // una orden que SOLO trae el número de ticket --que es el caso normal de
    // un caso importado-- escondía la tarjeta entera y el número no se veía
    // en ningún lado.
    if (ventana.isEmpty &&
        origen.isEmpty &&
        seguridad.isEmpty &&
        trabajo.numeroTicket.isEmpty) {
      return const SizedBox.shrink();
    }

    return DexterCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.assignment_outlined,
                  size: 16, color: AppColors.secondary),
              const SizedBox(width: 6),
              Text(
                'El trabajo',
                style:
                    AppTypography.etiqueta.copyWith(color: AppColors.onSurface),
              ),
            ],
          ),
          if (seguridad.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            for (final String requisito in seguridad)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.only(bottom: AppSpacing.xs),
                padding: const EdgeInsets.all(AppSpacing.sm),
                decoration: const BoxDecoration(
                  color: AppColors.errorContainer,
                  borderRadius: AppRadius.brCampo,
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    const Icon(Icons.health_and_safety_outlined,
                        size: 16, color: AppColors.onErrorContainer),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Text(
                        requisito,
                        style: AppTypography.cuerpoChico.copyWith(
                          color: AppColors.onErrorContainer,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
          if (ventana.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            _lineaDeDato(
              icono: Icons.schedule,
              etiqueta: 'Franja prometida al cliente',
              valor: ventana,
            ),
          ],
          // EL TICKET DEL ISP, NO EL UUID DEL CASO. Acá decía
          // «Viene de · Case · 293f1eb8-958d-4ada-96af-731b2797e08c», que no
          // le sirve a nadie: la oficina y el técnico hablan de «el 93426».
          // El número entra a la ficha desde el 25/09/2026.
          if (trabajo.numeroTicket.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            _lineaDeDato(
              icono: Icons.confirmation_number_outlined,
              // La etiqueta va antes del número y en mayúsculas: es un
              // identificador, y quien lo busca lo busca por esa palabra.
              etiqueta: 'TICKET:',
              // El estado es el de ALLÁ, y puede no coincidir con el del CRM:
              // alguien pudo cerrarlo del otro lado.
              // El proveedor va en el valor y no en la etiqueta: el número
              // es lo que se lee primero, y de qué sistema es importa después.
              valor: <String>[
                '#${trabajo.numeroTicket}',
                if (trabajo.estadoTicketIsp.isNotEmpty) trabajo.estadoTicketIsp,
                if (trabajo.proveedorTicket.isNotEmpty) trabajo.proveedorTicket,
              ].join(' · '),
            ),
            if (trabajo.abiertoPorTicket.isNotEmpty)
              // Quién lo abrió cambia la conversación: no es lo mismo que lo
              // haya pedido el cliente a que lo haya abierto la oficina. Si el
              // cliente no sabe de qué le hablan, esto lo explica.
              _lineaDeDato(
                icono: Icons.person_outline,
                etiqueta: 'Lo abrió',
                valor: trabajo.abiertoPorTicket,
              ),
          ] else if (origen.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            _lineaDeDato(
              icono: Icons.alt_route,
              etiqueta: 'Viene de',
              valor: origen,
            ),
          ],
        ],
      ),
    );
  }

  /// Lo que el técnico necesita del equipo y de la red.
  ///
  /// Sale del contexto que el despacho congeló al crear la orden: la caja
  /// donde va a conectar y el serial del equipo del cliente. Sin esos dos
  /// datos, la primera media hora en el sitio se va en buscarlos.
  ///
  /// La potencia óptica todavía no está: la mide SmartOLT y ese puente no
  /// existe. Cuando exista va acá, con su hora al lado, porque una lectura
  /// vieja es peor que ninguna.
  Widget _datosTecnicos(TrabajoVista trabajo) {
    final String cto = trabajo.contexto['cto']?.toString() ?? '';
    final String serial = trabajo.serialOnu;
    if (cto.isEmpty && serial.isEmpty) return const SizedBox.shrink();

    return DexterCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.hub_outlined,
                  size: 16, color: AppColors.secondary),
              const SizedBox(width: 6),
              Text(
                'Datos técnicos',
                style:
                    AppTypography.etiqueta.copyWith(color: AppColors.onSurface),
              ),
            ],
          ),
          if (cto.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            _lineaDeDato(
              icono: Icons.settings_input_component,
              etiqueta: 'Caja de distribución',
              valor: cto,
              monoespaciada: true,
            ),
          ],
          if (serial.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            _lineaDeDato(
              icono: Icons.qr_code_2,
              etiqueta: 'Serial del equipo del cliente',
              valor: serial,
              monoespaciada: true,
            ),
          ],
        ],
      ),
    );
  }

  /// Una línea de dato: qué es, y el valor.
  ///
  /// Los identificadores van en monoespaciada porque se leen carácter por
  /// carácter y se comparan contra una etiqueta pegada en un equipo: ahí la
  /// diferencia entre O y 0 importa.
  Widget _lineaDeDato({
    required IconData icono,
    required String etiqueta,
    required String valor,
    bool monoespaciada = false,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Icon(icono, size: 16, color: AppColors.onSurfaceVariant),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(etiqueta, style: AppTypography.etiquetaChica),
              Text(
                valor,
                style: monoespaciada
                    ? AppTypography.datoChico
                        .copyWith(color: AppColors.onSurface)
                    : AppTypography.cuerpo.copyWith(
                        color: AppColors.onSurface,
                        fontWeight: FontWeight.w600,
                      ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _datosDelCliente(TrabajoVista trabajo) {
    return DexterCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.person_pin_circle, size: 16, color: AppColors.secondary),
              const SizedBox(width: 6),
              Text(
                'Cliente & Ubicación',
                style: AppTypography.etiqueta.copyWith(color: AppColors.onSurface),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Icon(
                Icons.location_on_outlined,
                size: 16,
                color: AppColors.azulAccion,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(trabajo.direccion, style: AppTypography.cuerpo),
              ),
            ],
          ),
          if (trabajo.telefono.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: <Widget>[
                const Icon(
                  Icons.phone_outlined,
                  size: 16,
                  color: AppColors.exito,
                ),
                const SizedBox(width: AppSpacing.sm),
                Text(trabajo.telefono, style: AppTypography.etiquetaGrande),
              ],
            ),
          ],
          // Cómo se entra al inmueble: torre, piso, apartamento. Lo carga el
          // despacho y evita la vuelta al portero.
          if (trabajo.detalleAcceso.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Padding(
              padding: const EdgeInsets.only(left: 24),
              child: Text(
                trabajo.detalleAcceso,
                style: AppTypography.etiquetaChica,
              ),
            ),
          ],
          // El número con el que el cliente se identifica cuando llama a
          // soporte: es el que va a citar si algo queda pendiente.
          if (trabajo.idAbonado.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: <Widget>[
                const Icon(Icons.badge_outlined,
                    size: 16, color: AppColors.onSurfaceVariant),
                const SizedBox(width: AppSpacing.sm),
                Text(trabajo.idAbonado, style: AppTypography.datoChico),
              ],
            ),
          ],
          const SizedBox(height: AppSpacing.sm),
          _ubicacion(trabajo),
          // El plan se muestra cuando la orden lo trae, no cuando hay
          // demostración: define contra qué velocidad se prueba el servicio
          // antes de dar el trabajo por bueno.
          if (trabajo.planContratado.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            _planContratado(),
          ],
          if (trabajo.familia != FamiliaTrabajo.otro) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Text(
              '${trabajo.familia.etiqueta} · ${trabajo.tipoCodigo}',
              style: AppTypography.etiquetaChica,
            ),
          ],
        ],
      ),
    );
  }

  /// El recuadro de ubicación del diseño.
  ///
  /// No hay proveedor de mapas ni permiso para abrir otra aplicación, pero las
  /// coordenadas de la orden **sí** son reales (`cliente.lat/lng`): se dibuja
  /// la retícula con el punto donde queda y se muestran los grados. Sin
  /// coordenadas se dice que faltan, en vez de pintar un mapa de adorno que
  /// haría creer que la ubicación está confirmada.
  Widget _ubicacion(TrabajoVista trabajo) {
    final bool ubicado = trabajo.latitud != null && trabajo.longitud != null;

    return SizedBox(
      height: 96,
      child: ClipRRect(
        borderRadius: AppRadius.brTarjeta,
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            const ColoredBox(color: AppColors.surfaceContainerHigh),
            const CustomPaint(painter: _Reticula()),
            Center(
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: AppColors.surface.withValues(alpha: 0.92),
                  borderRadius: BorderRadius.circular(AppRadius.circulo),
                  boxShadow: AppTheme.sombraNivel1,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Icon(
                      ubicado ? Icons.pin_drop : Icons.location_off,
                      size: 16,
                      color: ubicado ? AppColors.error : AppColors.outline,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      ubicado
                          ? '${trabajo.latitud!.toStringAsFixed(5)}, '
                                '${trabajo.longitud!.toStringAsFixed(5)}'
                          : 'Sin coordenadas en la orden',
                      style: ubicado
                          ? AppTypography.datoChico.copyWith(
                              color: AppColors.onSurface,
                            )
                          : AppTypography.etiquetaChica,
                    ),
                  ],
                ),
              ),
            ),
            if (widget.mostrarDatosFuturos)
              Positioned(
                left: AppSpacing.sm,
                top: AppSpacing.sm,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 6,
                    vertical: 2,
                  ),
                  decoration: const BoxDecoration(
                    color: AppColors.surfaceContainerLowest,
                    borderRadius: AppRadius.brChico,
                  ),
                  // CAMPO-DATA-003 · La zona, que la orden todavía no trae.
                  child: Text(
                    'Zona ${trabajo.zona.isEmpty ? _ejemploDe(trabajo).zona : trabajo.zona}',
                    style: AppTypography.etiquetaChica,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  /// El plan del cliente. Viene en `contexto`, que el despacho congela al
  /// crear la orden; si no vino, se cae al ejemplo (CAMPO-DATA-023).
  /// El plan, tal como vino. Vacío si la orden no lo trae: el bloque
  /// entonces no se dibuja, en vez de anunciar una velocidad de ejemplo que
  /// alguien usaría para decidir si el servicio quedó bien.
  String get _plan => _trabajo?.planContratado ?? '';

  /// CAMPO-DATA-023 · Qué tiene contratado el cliente.
  /// Qué tiene contratado el cliente, tal como vino en la orden.
  ///
  /// Sin el chip "+ Dexter TV" que estaba escrito a mano: nada dice que este
  /// cliente tenga televisión. Se veía sólo en demostración y pasó a verse
  /// siempre al mostrar el plan real, que es como los datos de ejemplo se
  /// escapan a producción.
  Widget _planContratado() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brCampo,
      ),
      child: Row(
        children: <Widget>[
          const Icon(Icons.router, size: 18, color: AppColors.secondary),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Plan Activo', style: AppTypography.etiquetaChica),
                Text(
                  _plan,
                  style: AppTypography.cuerpoChico.copyWith(
                    color: AppColors.onSurface,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// CAMPO-DATA-001, 011 y 012: telemetría de red. Ningún sistema la entrega
  /// para campo todavía; se ve solo en modo demostración.
  static String _hhmm(DateTime f) =>
      '${f.hour.toString().padLeft(2, '0')}:${f.minute.toString().padLeft(2, '0')}';

  /// La potencia óptica, con la forma del panel de SmartOLT y los colores de
  /// la aplicación: dos tarjetas, la que RECIBE la ONT y la que recibe la OLT.
  ///
  /// **Dato real desde el 24/09/2026.** Antes acá se dibujaba
  /// `FieldMockData.potenciaRxPrevia` (-28.9 dBm) con la etiqueta roja
  /// «ATENUACIÓN ALTA» **siempre**, sin mirar la bandera de demostración. Con
  /// la orden 1849 en la mano, la lectura real era -21.19 dBm y el veredicto
  /// `aceptable`: la pantalla le decía al técnico que la señal estaba mal
  /// cuando estaba bien, y lo mandaba a buscar una atenuación que no existía.
  ///
  /// **Los umbrales son los del motor, no los del panel del proveedor.** El
  /// panel de SmartOLT rotula `crit -30 · warn -28`; acá manda G-GO-04, que
  /// declara aceptable entre -8 y -25 dBm. Dibujar la regla del proveedor al
  /// lado de un veredicto calculado con otra haría que la barra y la etiqueta
  /// se contradigan en los casos de borde, que son justo los que importan.
  /// El veredicto **no se recalcula acá**: llega resuelto
  /// (`onu_signal_1490_veredicto`) y la pantalla lo muestra.
  Widget _potenciaOptica(TrabajoVista trabajo) {
    if (!trabajo.hayLecturaDeEquipo) {
      // El ejemplo solo aparece donde NO hay lectura real, y solo con la
      // demostración encendida. Esa es toda la diferencia con lo que había
      // antes: el valor de ejemplo ya no puede taparle la señal a nadie.
      return widget.mostrarDatosFuturos
          ? _potenciaDeEjemplo()
          : _sinLecturaDeEquipo(trabajo);
    }

    final bool aceptable = trabajo.veredictoSenal == 'aceptable';

    return Column(
      children: <Widget>[
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Expanded(
              child: _MedidaOptica(
                titulo: 'Rx ONU',
                detalle: 'lo que recibe el equipo del cliente',
                valor: trabajo.potenciaOptica,
                // El veredicto del motor es sobre 1490: es la de bajada, la
                // única que habla de lo que llega a la casa.
                etiqueta: trabajo.veredictoSenal,
                buena: aceptable,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: _MedidaOptica(
                titulo: 'Rx OLT',
                detalle: 'lo que la central recibe del equipo',
                valor: trabajo.potenciaOpticaSubida,
                // Sin etiqueta: el motor no emite veredicto para la de
                // subida, y ponerle uno acá sería inventarlo.
                etiqueta: '',
                buena: aceptable,
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Aceptable entre -8 y -25 dBm (G-GO-04)',
          style: AppTypography.etiquetaChica.copyWith(color: AppColors.outline),
        ),
      ],
    );
  }


  /// Un ping en vivo, que es lo único que la ficha congelada no puede
  /// contestar: el técnico movió un conector y necesita saber si el equipo
  /// responde AHORA.
  ///
  /// **Diez paquetes, listados uno por uno.** Un promedio esconde lo que le
  /// interesa a quien está parado en la casa —si el enlace es intermitente o
  /// está caído parejo—, y con tres muestras esa diferencia no se dibuja:
  /// está medido que el mismo equipo sano devuelve 1, 2 y 3 de 3 en corridas
  /// seguidas, así que una racha corta no se distingue de un patrón.
  ///
  /// **No dictamina.** Se enseña el conteo crudo y cada intento; quien decide
  /// qué significa es la persona que está ahí.
  Widget _probarConexion() {
    final bool disponible = widget.acciones.probarConexion != null;
    final ResultadoPing? r = _ping;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.network_ping, size: 18,
                  color: AppColors.secondary),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text('Ping', style: AppTypography.cuerpoChico),
              ),
              if (_pingEnCurso) ...<Widget>[
                Text(
                  _ping == null
                      ? '$_paquetesDelPing paquetes…'
                      : '${_ping!.paquetes.length} de $_paquetesDelPing…',
                  style: AppTypography.etiquetaChica,
                ),
                const SizedBox(width: AppSpacing.sm),
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ] else ...<Widget>[
                TextButton(
                  onPressed: disponible ? _lanzarPing : null,
                  child: Text(r == null ? 'Ping' : 'Repetir'),
                ),
                // Cerrar el resultado. No es cosmética: la lista ocupa media
                // pantalla y debajo está el botón con el que el técnico
                // avanza la orden.
                if (r != null)
                  IconButton(
                    onPressed: () => setState(() => _ping = null),
                    icon: const Icon(Icons.close, size: 18),
                    tooltip: 'Cerrar el resultado',
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ],
          ),
          if (r != null) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            if (r.medido) ...<Widget>[
              Text(
                'Respondieron ${r.respondieron}',
                style: AppTypography.datoChico.copyWith(
                  color: AppColors.onSurface,
                ),
              ),
              const SizedBox(height: AppSpacing.xs),
              for (final PaqueteDePing p in r.paquetes)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 1),
                  child: Row(
                    children: <Widget>[
                      SizedBox(
                        width: 26,
                        child: Text('${p.n}.',
                            style: AppTypography.etiquetaChica),
                      ),
                      Icon(
                        p.respondio ? Icons.check_circle : Icons.cancel,
                        size: 13,
                        color: p.respondio ? AppColors.exito : AppColors.error,
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          p.respondio
                              ? (p.rtt.isEmpty ? 'volvió' : p.rtt)
                              : 'sin respuesta',
                          style: AppTypography.datoChico.copyWith(
                            color: p.respondio
                                ? AppColors.onSurface
                                : AppColors.error,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
            ] else
              Text(
                // Cada motivo se arregla distinto, así que cada uno dice lo
                // suyo. «No se pudo medir» jamás se dibuja como «no
                // respondió»: esa confusión manda a revisar una roseta sana.
                switch (r.motivo) {
                  'sin_conexion' =>
                    'Sin conexión: esta prueba necesita señal y no se encola. '
                        'Se puede repetir cuando haya.',
                  'ping_no_habilitado' =>
                    'La prueba no está habilitada para esta empresa todavía.',
                  'motor_no_responde' =>
                    'No se pudo preguntar. No dice nada del equipo del cliente.',
                  _ => 'No se pudo medir.',
                },
                style: AppTypography.etiquetaChica.copyWith(
                  color: AppColors.onSurfaceVariant,
                ),
              ),
          ],
        ],
      ),
    );
  }

  /// Pide las tandas en orden y va agregando cada una apenas llega, para que
  /// los paquetes se vean caer en vez de aparecer los diez al final.
  ///
  /// Si una tanda falla, se corta ahí y se muestra el motivo **conservando lo
  /// que ya volvió**: cinco paquetes medidos y una explicación valen más que
  /// una pantalla en blanco.
  Future<void> _lanzarPing() async {
    final Future<ResultadoPing> Function(String, int)? probar =
        widget.acciones.probarConexion;
    if (probar == null || _pingEnCurso) return;

    setState(() {
      _pingEnCurso = true;
      // El resultado anterior se borra al arrancar: dejarlo en pantalla
      // mientras corre el siguiente invita a leer el viejo como el nuevo.
      _ping = null;
    });

    final List<PaqueteDePing> acumulados = <PaqueteDePing>[];
    for (final int tanda in _tandasDelPing) {
      final ResultadoPing r = await probar(widget.ordenId, tanda);
      if (!mounted) return;

      if (!r.medido) {
        setState(() {
          _pingEnCurso = false;
          // Lo que ya se midió no se tira: se muestra con el motivo al lado.
          _ping = acumulados.isEmpty
              ? r
              : ResultadoPing(
                  medido: true,
                  respondieron: _conteo(acumulados),
                  paquetes: List<PaqueteDePing>.of(acumulados),
                  motivo: r.motivo,
                );
        });
        return;
      }

      // Se renumeran de corrido: cada tanda vuelve empezando en 1, y una
      // lista que dijera 1,2,3,1,2,3 sería ilegible.
      for (final PaqueteDePing p in r.paquetes) {
        acumulados.add(PaqueteDePing(
          n: acumulados.length + 1,
          respondio: p.respondio,
          rtt: p.rtt,
          perdida: p.perdida,
        ));
      }
      setState(() {
        _ping = ResultadoPing(
          medido: true,
          respondieron: _conteo(acumulados),
          paquetes: List<PaqueteDePing>.of(acumulados),
        );
      });
    }

    if (mounted) setState(() => _pingEnCurso = false);
  }

  /// «X de Y» con lo que se lleva medido. Se cuenta acá y no se reenvía el
  /// texto de una tanda: cada una dice «3 de 3», y pegar el de la última haría
  /// que diez paquetes con dos perdidos se anuncien como «4 de 4».
  static String _conteo(List<PaqueteDePing> ps) =>
      '${ps.where((PaqueteDePing p) => p.respondio).length} de ${ps.length}';

  /// CAMPO-DATA-001 · La potencia de ejemplo, para ver el producto completo
  /// cuando la orden todavía no trae lectura. Es el bloque que estaba acá
  /// antes, intacto: lo único que cambió es **cuándo** se dibuja.
  Widget _potenciaDeEjemplo() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: const BoxDecoration(
        color: AppColors.errorContainer,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Row(
        children: <Widget>[
          const Icon(
            Icons.warning,
            size: 18,
            color: AppColors.onErrorContainer,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Flexible(
                      child: Text(
                        'Potencia RX ONT Actual',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: AppTypography.etiquetaChica.copyWith(
                          color: AppColors.onErrorContainer,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 5,
                        vertical: 1,
                      ),
                      decoration: const BoxDecoration(
                        color: AppColors.error,
                        borderRadius: AppRadius.brChico,
                      ),
                      child: Text(
                        'ATENUACIÓN ALTA',
                        style: AppTypography.etiquetaChica.copyWith(
                          fontSize: 9,
                          color: AppColors.onError,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
                Text(
                  FieldMockData.rangoOptimoTexto,
                  style: AppTypography.etiquetaChica.copyWith(
                    color: AppColors.onErrorContainer,
                  ),
                ),
              ],
            ),
          ),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: <Widget>[
              Text(
                FieldMockData.potenciaRxPrevia.toStringAsFixed(1),
                style: AppTypography.medicion.copyWith(color: AppColors.error),
              ),
              const SizedBox(width: 2),
              Text(
                'dBm',
                style: AppTypography.etiquetaChica.copyWith(
                  color: AppColors.onErrorContainer,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Por qué no hay lectura, que no es lo mismo que una tarjeta vacía.
  ///
  /// Una tarjeta en blanco manda a buscar una falla de red donde lo único que
  /// pasa es que falta cargar un serial — y eso le ocurre a 1.299 de 4.163
  /// clientes activos, medido. Cada motivo se arregla distinto, así que cada
  /// uno dice lo suyo.
  Widget _sinLecturaDeEquipo(TrabajoVista trabajo) {
    final (IconData icono, String texto) = switch (trabajo.sinEquipo) {
      SinEquipo.serialNoCargado => (
          Icons.link_off,
          'Este cliente no tiene el equipo cargado en el sistema, así que no '
              'hay señal que consultar. No es una falla de red.',
        ),
      SinEquipo.serialDesactualizado => (
          Icons.sync_problem,
          'El serial que figura no existe en la OLT. Suele pasar cuando se le '
              'cambió el equipo al cliente y se actualizó un solo sistema.',
        ),
      _ => (
          Icons.cloud_off,
          'La señal del equipo no se alcanzó a leer. Se vuelve a intentar al '
              'refrescar la ficha.',
        ),
    };

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(icono, size: 18, color: AppColors.outline),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              texto,
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _telemetria(TrabajoVista trabajo) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                width: 32,
                height: 32,
                decoration: const BoxDecoration(
                  color: AppColors.surfaceContainer,
                  borderRadius: AppRadius.brCampo,
                ),
                child: const Icon(
                  Icons.router,
                  size: 18,
                  color: AppColors.secondary,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      'Telemetría SmartOLT',
                      style: AppTypography.cuerpoGrande,
                    ),
                    Text('Vía Dexter API', style: AppTypography.etiquetaChica),
                  ],
                ),
              ),
              // La lectura está CONGELADA, no en vivo. Acá decía "Live" con un
              // punto verde sobre datos capturados horas antes. El backend ya
              // dejó escrito por qué importa: "al congelarse, una medición deja
              // de ser una medición -- pasa a ser un registro de lo que se veía
              // en un momento". Un técnico parado en la casa que lee "Live" no
              // tiene forma de saber que está viendo el pasado.
              if (trabajo.fichaCapturadaEn != null)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                  decoration: const BoxDecoration(
                    color: AppColors.surfaceContainerHigh,
                    borderRadius: AppRadius.brChico,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      const Icon(
                        Icons.history,
                        size: 11,
                        color: AppColors.outline,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        'Medido ${_hhmm(trabajo.fichaCapturadaEn!)}',
                        style: AppTypography.etiquetaChica,
                      ),
                    ],
                  ),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          // El serial va SOLO en su fila: doce caracteres no entran en media
          // pantalla sin partirse, y es la única llave con la que se llega a
          // SmartOLT -- si se corta, no sirve para buscar nada.
          _CajaDato(
            titulo: 'ONT SERIAL',
            valor: trabajo.serialOnu.isNotEmpty
                ? trabajo.serialOnu
                : (widget.mostrarDatosFuturos ? FieldMockData.serialOnt : '—'),
            detalle: trabajo.estadoOnu.isNotEmpty
                ? 'Equipo ${trabajo.estadoOnu}'
                : 'Sin lectura',
          ),
          const SizedBox(height: AppSpacing.sm),
          // CAMPO-DATA-011, ya no es de ejemplo: el puerto PON y la caja
          // entran a la ficha desde el 25/09/2026 (api.py::_estado_equipo,
          // con lista blanca -- esa respuesta trae el nombre del cliente).
          //
          // DOS TARJETAS Y NO UNA. Estaban juntas bajo «PUERTO PON / CAJA» y
          // se leía mal: el valor grande era el puerto y la caja quedaba
          // debajo como si fuera su detalle. Son dos datos distintos, de dos
          // cosas distintas de la red, y cada uno puede faltar por su cuenta.
          Row(
            children: <Widget>[
              Expanded(
                child: _CajaDato(
                  titulo: 'PUERTO PON',
                  valor: trabajo.puertoPon.isNotEmpty
                      ? trabajo.puertoPon
                      : (widget.mostrarDatosFuturos
                          ? FieldMockData.puertoPon
                          : '—'),
                  // 'board/port'. El número de ONU va aparte: es su posición
                  // DENTRO del puerto, no parte del identificador.
                  detalle: trabajo.puertoPon.isNotEmpty
                      ? 'tarjeta / puerto'
                      : 'Dato no disponible',
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              // La CAJA puede venir vacía y es normal, no un fallo: medido, el
              // cliente de la orden 1849 no la tiene cargada en SmartOLT. Se
              // dice, en vez de dibujar una que no existe.
              Expanded(
                child: _CajaDato(
                  titulo: 'CAJA / CTO',
                  valor: trabajo.cajaDeDistribucion.isNotEmpty
                      ? trabajo.cajaDeDistribucion
                      : '—',
                  detalle: trabajo.cajaDeDistribucion.isNotEmpty
                      ? 'caja de distribución'
                      : 'Sin caja cargada',
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          _potenciaOptica(trabajo),
          const SizedBox(height: AppSpacing.sm),
          // La planta, con lo que la ficha capturó de verdad. Cada fila
          // aparece solo si su dato llegó: una etiqueta con un guion al lado
          // ocupa el mismo lugar y no informa nada.
          for (final (String titulo, String valor) in <(String, String)>[
            ('OLT', trabajo.oltDelEquipo),
            // El número de ONU va acá y no pegado al puerto: es su posición
            // DENTRO del PON, no parte del identificador del puerto.
            ('ONU en el puerto', trabajo.indiceOnu),
            ('Zona de red', trabajo.zonaDeRed),
            ('Equipo', trabajo.modeloDelEquipo),
            ('Distancia a la OLT', trabajo.distanciaOlt),
          ])
            if (valor.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(titulo, style: AppTypography.etiquetaChica),
                    ),
                    Text(
                      valor,
                      style: AppTypography.datoChico.copyWith(
                        color: AppColors.onSurface,
                      ),
                    ),
                  ],
                ),
              ),
          const SizedBox(height: AppSpacing.sm),
          _probarConexion(),
          const SizedBox(height: AppSpacing.sm),
          // CAMPO-DATA-012 y -030 · El historico de 48 horas no llega de
          // ningun lado: la ficha congela UNA lectura, no una serie. Dibujar
          // una curva de ejemplo al lado de una potencia REAL la haria pasar
          // por el historico de este cliente.
          if (widget.mostrarDatosFuturos) ...<Widget>[
          // CAMPO-DATA-012
          Container(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
            decoration: const BoxDecoration(
              color: AppColors.surfaceContainerLow,
              borderRadius: AppRadius.brCampo,
            ),
            child: Row(
              children: <Widget>[
                Text('Histórico 48h', style: AppTypography.etiquetaChica),
                const SizedBox(width: AppSpacing.sm),
                // CAMPO-DATA-030 · La serie de las últimas 48 horas.
                const Expanded(
                  child: SizedBox(
                    height: 28,
                    child: CustomPaint(
                      painter: _CurvaRx(FieldMockData.historicoRx48h),
                      size: Size.infinite,
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                const Icon(
                  Icons.trending_down,
                  size: 16,
                  color: AppColors.error,
                ),
                const SizedBox(width: 4),
                Text(
                  '${FieldMockData.deltaPotencia48h} dBm',
                  style: AppTypography.etiqueta.copyWith(
                    color: AppColors.error,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          // CAMPO-DATA-048 · La matriz completa del diseño: de qué OLT cuelga,
          // por qué puerto, a qué distancia y con cuánta potencia sale.
          for (final (String titulo, String valor) in <(String, String)>[
            ('OLT & Puerto', FieldMockData.oltYPuerto),
            ('CTO Distribución', FieldMockData.terminal),
            ('Distancia Splitter', FieldMockData.distanciaSplitter),
            ('Potencia TX OLT', FieldMockData.potenciaTxOlt),
          ])
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                children: <Widget>[
                  Expanded(
                    child: Text(titulo, style: AppTypography.etiquetaChica),
                  ),
                  Text(
                    valor,
                    style: AppTypography.datoChico.copyWith(
                      color: AppColors.onSurface,
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: AppSpacing.xs),
          Text(
            trabajo.fichaCapturadaEn == null
                ? 'Fuente: SmartOLT vía Dexter API'
                : 'Fuente: SmartOLT vía Dexter API · lectura congelada al '
                    'despachar, no es la señal de este momento',
            style: AppTypography.etiquetaChica.copyWith(
              color: AppColors.outline,
              fontSize: 10,
            ),
          ),
        ],
      ),
    );
  }

  /// Lo que el asistente ya averiguó, antes de que existiera esta orden.
  ///
  /// **Es trabajo hecho que se estaba tirando.** Dexter habla con el cliente
  /// por WhatsApp: verifica identidad, mide el equipo, descarta causas y deja
  /// escrito qué falta averiguar. Todo eso vivía en su base y no salía de ahí,
  /// así que el técnico llegaba a la casa a preguntar lo que el cliente ya
  /// había contestado.
  ///
  /// El «siguiente paso» va arriba y destacado: no es una etiqueta, es la
  /// instrucción concreta con la que conviene tocar el timbre.
  ///
  /// El resumen viaja **sin el documento del cliente** (lo redacta el modelo y
  /// trae la cédula cuando la verificó). Ver `_sin_documentos` en el backend.
  Widget _loQueDexterAveriguo(TrabajoVista trabajo) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.auto_awesome, size: 18,
                  color: AppColors.primary),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text('Lo que el asistente ya averiguó',
                    style: AppTypography.cuerpoGrande),
              ),
              if (trabajo.motivoEscaladaDexter.isNotEmpty)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                  decoration: const BoxDecoration(
                    color: AppColors.surfaceContainerHigh,
                    borderRadius: AppRadius.brChico,
                  ),
                  child: Text(
                    trabajo.motivoEscaladaDexter.replaceAll('_', ' '),
                    style: AppTypography.etiquetaChica,
                  ),
                ),
            ],
          ),
          if (trabajo.siguientePasoDexter.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: const BoxDecoration(
                color: AppColors.surfaceContainer,
                borderRadius: AppRadius.brCampo,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'QUÉ FALTA AVERIGUAR',
                    style: AppTypography.etiquetaChica.copyWith(
                      fontWeight: FontWeight.w700,
                      color: AppColors.primary,
                      letterSpacing: 0.5,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    trabajo.siguientePasoDexter,
                    style: AppTypography.cuerpoChico,
                  ),
                ],
              ),
            ),
          ],
          if (trabajo.resumenDexter.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Text(trabajo.resumenDexter,
                style: AppTypography.datoChico.copyWith(
                  color: AppColors.onSurfaceVariant,
                )),
          ],
          if (trabajo.casoDexter.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Clasificado como ${trabajo.casoDexter.replaceAll('_', ' ')}',
              style: AppTypography.etiquetaChica
                  .copyWith(color: AppColors.outline),
            ),
          ],
        ],
      ),
    );
  }

  /// El triage del diseño. La cita del cliente es **real** —es el diagnóstico
  /// que manda el backend—; la lista de comprobaciones y la causa sugerida son
  /// de ejemplo (CAMPO-DATA-024) hasta que exista un diagnóstico estructurado.
  Widget _triage(TrabajoVista trabajo) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                width: 32,
                height: 32,
                decoration: const BoxDecoration(
                  color: AppColors.surfaceContainer,
                  borderRadius: AppRadius.brCampo,
                ),
                child: const Icon(
                  Icons.smart_toy,
                  size: 18,
                  color: AppColors.primary,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      'Triage Inteligente Dexter',
                      style: AppTypography.cuerpoGrande,
                    ),
                    Text(
                      widget.mostrarDatosFuturos
                          ? 'Análisis correlacionado en tiempo real'
                          : 'Lo que trae la orden',
                      style: AppTypography.etiquetaChica,
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (trabajo.diagnosticoPrevio.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            Container(
              padding: const EdgeInsets.all(AppSpacing.sm),
              decoration: const BoxDecoration(
                color: AppColors.surfaceContainerLow,
                borderRadius: AppRadius.brCampo,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const Icon(
                    Icons.record_voice_over,
                    size: 16,
                    color: AppColors.onSurfaceVariant,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      trabajo.diagnosticoPrevio,
                      style: AppTypography.cuerpo.copyWith(
                        fontStyle: FontStyle.italic,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
          if (widget.mostrarDatosFuturos) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            const _FilaChequeo(
              icono: Icons.verified,
              texto: 'Facturación y perfil de cliente',
              estado: 'AL DÍA',
              color: AppColors.exito,
            ),
            const _FilaChequeo(
              icono: Icons.cell_tower,
              texto: 'Puerto OLT PON 0/1/4',
              estado: 'NORMAL',
              color: AppColors.exito,
            ),
            const _FilaChequeo(
              icono: Icons.error_outline,
              texto: 'Atenuación acumulada',
              estado: 'DEGRADADO',
              color: AppColors.error,
            ),
            const SizedBox(height: AppSpacing.sm),
            Container(
              padding: const EdgeInsets.all(AppSpacing.sm),
              decoration: const BoxDecoration(
                color: AppColors.surfaceContainerHigh,
                borderRadius: AppRadius.brCampo,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const Icon(
                    Icons.lightbulb,
                    size: 16,
                    color: AppColors.primary,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          'CAUSA SUGERIDA',
                          style: AppTypography.etiquetaChica.copyWith(
                            color: AppColors.primary,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        Text(
                          'Conector SC/APC sucio, fisura interna o radio de '
                          'curvatura estrangulado en acometida.',
                          style: AppTypography.cuerpoChico,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _avisoExcepcion(TrabajoVista trabajo, LecturaDePasos lectura) {
    final esCancelada = trabajo.estado == EstadoTrabajo.cancelada;
    return DexterCard(
      colorFondo: esCancelada
          ? AppColors.inactivoFondo
          : AppColors.precaucionFondo,
      colorBorde: esCancelada ? AppColors.bordeFuerte : AppColors.precaucion,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            esCancelada ? Icons.block : Icons.assignment_return_outlined,
            size: 18,
            color: esCancelada ? AppColors.inactivo : AppColors.precaucion,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(lectura.avisoExcepcion!, style: AppTypography.cuerpo),
          ),
        ],
      ),
    );
  }

  /// Terminada en el teléfono, sin confirmar el servidor. La diferencia
  /// importa: hasta que la cola no la envíe, para la empresa ese trabajo no
  /// está hecho.
  Widget _avisoSinEnviar() {
    return DexterCard(
      colorFondo: AppColors.precaucionFondo,
      colorBorde: AppColors.precaucion,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.cloud_upload_outlined,
                size: 18,
                color: AppColors.precaucion,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  'Completado en campo · pendiente de enviar',
                  style: AppTypography.cuerpoGrande,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Lo que hiciste está guardado en el teléfono. Se envía solo cuando '
            'haya señal; no hace falta repetirlo.',
            style: AppTypography.cuerpoChico,
          ),
        ],
      ),
    );
  }

  Widget _acciones(TrabajoVista trabajo, AccionesDisponibles acciones) {
    if (trabajo.requiereActualizacion) {
      return const ElevatedButton(
        onPressed: null,
        child: Text('Actualizá la aplicación para trabajar esta orden'),
      );
    }

    if (acciones.primaria == null) {
      return Text(
        _sinAccionesPorque(trabajo.estado),
        style: AppTypography.cuerpoChico,
        textAlign: TextAlign.center,
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        ElevatedButton(
          onPressed: _trabajando
              ? null
              : () => _ejecutarAccion(trabajo, acciones.primaria!),
          child: _trabajando
              ? const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Text(acciones.primaria!.etiqueta),
        ),
        for (final AccionOrden secundaria in acciones.secundarias) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          OutlinedButton(
            onPressed: _trabajando
                ? null
                : () => _ejecutarAccion(trabajo, secundaria),
            child: Text(secundaria.etiqueta),
          ),
        ],
      ],
    );
  }

  String _sinAccionesPorque(EstadoTrabajo estado) => switch (estado) {
    EstadoTrabajo.completadaSinEnviar =>
      'Ya está hecho. Falta que se envíe al servidor.',
    EstadoTrabajo.completadaCampo =>
      'Trabajo entregado. Queda esperar la revisión del supervisor.',
    EstadoTrabajo.cerrada => 'Este trabajo está cerrado.',
    EstadoTrabajo.cancelada => 'Este trabajo fue cancelado.',
    _ => 'No hay ninguna acción disponible para este estado.',
  };
}

/// La línea de pasos del diseño, alimentada por [LecturaDePasos].
class _BarraDePasos extends StatelessWidget {
  const _BarraDePasos({required this.lectura});

  final LecturaDePasos lectura;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: lectura.pasoActual < 0
          ? 'Sin avance'
          : 'Paso ${lectura.pasoActual + 1} de ${PasoOrden.values.length}: '
                '${PasoOrden.values[lectura.pasoActual].etiqueta}',
      excludeSemantics: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              for (int i = 0; i < PasoOrden.values.length; i++) ...<Widget>[
                if (i > 0) const SizedBox(width: AppSpacing.xs),
                Expanded(
                  child: Container(
                    height: 4,
                    decoration: BoxDecoration(
                      color: _colorDelPaso(i),
                      borderRadius: AppRadius.brChico,
                    ),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              for (int i = 0; i < PasoOrden.values.length; i++) ...<Widget>[
                if (i > 0) const SizedBox(width: AppSpacing.xs),
                Expanded(
                  child: Column(
                    children: <Widget>[
                      if (i < lectura.pasoActual)
                        const Icon(
                          Icons.check,
                          size: 11,
                          color: AppColors.exito,
                        ),
                      Text(
                        PasoOrden.values[i].etiqueta,
                        textAlign: TextAlign.center,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: AppTypography.etiquetaChica.copyWith(
                          fontSize: 10,
                          height: 1.1,
                          color: i == lectura.pasoActual
                              ? AppColors.primary
                              : AppColors.onSurfaceVariant,
                          fontWeight: i == lectura.pasoActual
                              ? FontWeight.w700
                              : FontWeight.w400,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Color _colorDelPaso(int indice) {
    if (lectura.pasoActual < 0) return AppColors.borde;
    if (indice > lectura.pasoActual) return AppColors.borde;
    // El paso donde está parada una orden devuelta se pinta en ámbar: llegó
    // hasta ahí, pero no por el camino normal.
    if (indice == lectura.pasoActual && lectura.excepcion) {
      return AppColors.precaucion;
    }
    return AppColors.azulMarino;
  }
}

/// Una casilla de dato técnico, como las del diseño.
class _CajaDato extends StatelessWidget {
  const _CajaDato({
    required this.titulo,
    required this.valor,
    required this.detalle,
  });

  final String titulo;
  final String valor;
  final String detalle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brCampo,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(titulo, style: AppTypography.etiquetaChica),
          const SizedBox(height: 2),
          Text(
            valor,
            style: AppTypography.etiquetaGrande.copyWith(
              color: AppColors.onSurface,
              fontWeight: FontWeight.w700,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          Text(
            detalle,
            style: AppTypography.etiquetaChica,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

/// Una línea de la lista de comprobaciones del triage.
class _FilaChequeo extends StatelessWidget {
  const _FilaChequeo({
    required this.icono,
    required this.texto,
    required this.estado,
    required this.color,
  });

  final IconData icono;
  final String texto;
  final String estado;
  final Color color;

  /// La fila degradada se pinta entera: es la que hay que mirar primero.
  bool get _esAlerta => color == AppColors.error;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.xs),
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: _esAlerta
            ? AppColors.errorContainer
            : AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brCampo,
      ),
      child: Row(
        children: <Widget>[
          Icon(icono, size: 16, color: color),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              texto,
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onSurface,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Text(
            estado,
            style: AppTypography.etiquetaChica.copyWith(
              color: color,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

/// CAMPO-DATA-030 · La curva de potencia de las últimas 48 horas.
///
/// Dibuja la serie tal cual llega, sin suavizar ni recortar: si alguna vez
/// llegan lecturas reales, lo que se ve es lo que midió la OLT.
class _CurvaRx extends CustomPainter {
  const _CurvaRx(this.serie);

  final List<double> serie;

  @override
  void paint(Canvas lienzo, Size medida) {
    if (serie.length < 2) return;

    final double minimo = serie.reduce((double a, double b) => a < b ? a : b);
    final double maximo = serie.reduce((double a, double b) => a > b ? a : b);
    final double rango = (maximo - minimo).abs() < 0.01 ? 1 : maximo - minimo;

    final Path camino = Path();
    for (int i = 0; i < serie.length; i++) {
      final double x = medida.width * i / (serie.length - 1);
      final double y = medida.height * (1 - (serie[i] - minimo) / rango);
      if (i == 0) {
        camino.moveTo(x, y);
      } else {
        camino.lineTo(x, y);
      }
    }

    lienzo.drawPath(
      camino,
      Paint()
        ..color = AppColors.error
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5
        ..strokeCap = StrokeCap.round,
    );

    // El último punto, que es la lectura de ahora.
    lienzo.drawCircle(
      Offset(medida.width, medida.height * (1 - (serie.last - minimo) / rango)),
      2.5,
      Paint()..color = AppColors.error,
    );
  }

  @override
  bool shouldRepaint(_CurvaRx anterior) => anterior.serie != serie;
}

/// Una acción rápida del detalle. Cuando no hay con qué —sin teléfono, sin
/// coordenadas— se ve apagada en vez de fallar al tocarla.
class _AccionRapidaDetalle extends StatelessWidget {
  const _AccionRapidaDetalle({
    required this.icono,
    required this.texto,
    required this.activa,
    this.alTocar,
  });

  final IconData icono;
  final String texto;
  final bool activa;
  final VoidCallback? alTocar;

  @override
  Widget build(BuildContext context) {
    final Color color = activa ? AppColors.primary : AppColors.outline;

    return Semantics(
      button: true,
      enabled: activa,
      label: activa ? texto : '$texto: no disponible',
      excludeSemantics: true,
      child: Material(
        color: activa
            ? AppColors.surfaceContainerLowest
            : AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
        child: InkWell(
          borderRadius: AppRadius.brTarjeta,
          onTap: alTocar,
          child: Container(
            height: AppSpacing.objetivoTactil,
            decoration: BoxDecoration(
              borderRadius: AppRadius.brTarjeta,
              boxShadow: activa ? AppTheme.sombraNivel1 : null,
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                Icon(icono, size: 16, color: color),
                Text(
                  texto,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.etiquetaChica.copyWith(color: color),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// La retícula del recuadro de ubicación. No es un mapa: es el fondo sobre el
/// que se leen las coordenadas, para que nadie lo confunda con una calle.
class _Reticula extends CustomPainter {
  const _Reticula();

  @override
  void paint(Canvas lienzo, Size medida) {
    final Paint linea = Paint()
      ..color = AppColors.surfaceContainerLowest.withValues(alpha: 0.6)
      ..strokeWidth = 1;

    for (double x = 0; x < medida.width; x += 24) {
      lienzo.drawLine(Offset(x, 0), Offset(x, medida.height), linea);
    }
    for (double y = 0; y < medida.height; y += 24) {
      lienzo.drawLine(Offset(0, y), Offset(medida.width, y), linea);
    }
  }

  @override
  bool shouldRepaint(_Reticula anterior) => false;
}

/// Una medida óptica con la forma del panel de SmartOLT —valor grande,
/// etiqueta de estado y una barra con la zona buena— y los colores de esta
/// aplicación.
///
/// La barra usa los umbrales de **G-GO-04**, no los del panel del proveedor
/// (`crit -30 · warn -28`). Mezclarlos haría que la barra contradiga al
/// veredicto en los casos de borde, que son los únicos en los que alguien
/// mira la barra.
class _MedidaOptica extends StatelessWidget {
  const _MedidaOptica({
    required this.titulo,
    required this.detalle,
    required this.valor,
    required this.etiqueta,
    required this.buena,
  });

  final String titulo;
  final String detalle;

  /// Como lo manda SmartOLT: '-21.19 dBm'.
  final String valor;

  /// El veredicto del motor, o vacío si no emitió ninguno para esta medida.
  final String etiqueta;
  final bool buena;

  /// Los bordes de la zona aceptable, en dBm.
  static const double _min = -25.0;
  static const double _max = -8.0;

  /// Hasta dónde se dibuja la regla. No empieza en el umbral: una barra que
  /// arranca justo donde termina lo aceptable no deja ver CUÁNTO se pasó.
  static const double _pisoRegla = -32.0;
  static const double _techoRegla = -4.0;

  double? get _numero {
    final String limpio = valor.replaceAll(RegExp(r'[^0-9.\-]'), '');
    return double.tryParse(limpio);
  }

  @override
  Widget build(BuildContext context) {
    final double? dbm = _numero;
    final bool hay = dbm != null;
    final Color acento = buena ? AppColors.exito : AppColors.error;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: buena ? AppColors.exitoFondo : AppColors.errorContainer,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            titulo.toUpperCase(),
            style: AppTypography.etiquetaChica.copyWith(
              fontWeight: FontWeight.w700,
              color: buena ? AppColors.exitoTexto : AppColors.onErrorContainer,
            ),
          ),
          const SizedBox(height: 2),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: <Widget>[
              Text(
                hay ? dbm.toStringAsFixed(2) : '—',
                style: AppTypography.medicion.copyWith(color: acento),
              ),
              const SizedBox(width: 2),
              Text(
                'dBm',
                style: AppTypography.etiquetaChica.copyWith(
                  color: buena
                      ? AppColors.exitoTexto
                      : AppColors.onErrorContainer,
                ),
              ),
            ],
          ),
          if (etiqueta.isNotEmpty) ...<Widget>[
            const SizedBox(height: 4),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: acento,
                borderRadius: AppRadius.brChico,
              ),
              child: Text(
                etiqueta.replaceAll('_', ' ').toUpperCase(),
                style: AppTypography.etiquetaChica.copyWith(
                  fontSize: 9,
                  color: AppColors.onError,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
          if (hay) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            SizedBox(
              height: 10,
              child: CustomPaint(
                painter: _ReglaOptica(
                  dbm: dbm,
                  min: _min,
                  max: _max,
                  piso: _pisoRegla,
                  techo: _techoRegla,
                  marca: acento,
                ),
                size: Size.infinite,
              ),
            ),
          ],
          const SizedBox(height: 4),
          Text(
            detalle,
            style: AppTypography.etiquetaChica.copyWith(
              fontSize: 10,
              color: buena ? AppColors.exitoTexto : AppColors.onErrorContainer,
            ),
          ),
        ],
      ),
    );
  }
}

/// La regla de la medida: la franja verde es la zona aceptable y la marca es
/// dónde cayó esta lectura. Fuera de la regla, la marca se queda en el borde
/// en vez de salirse: decir «está fuera» es la información; cuánto más allá,
/// no cambia lo que hace el técnico.
class _ReglaOptica extends CustomPainter {
  const _ReglaOptica({
    required this.dbm,
    required this.min,
    required this.max,
    required this.piso,
    required this.techo,
    required this.marca,
  });

  final double dbm;
  final double min;
  final double max;
  final double piso;
  final double techo;
  final Color marca;

  double _x(double v, double ancho) =>
      ((v - piso) / (techo - piso)).clamp(0.0, 1.0) * ancho;

  @override
  void paint(Canvas lienzo, Size medida) {
    final double alto = medida.height;
    final RRect fondo = RRect.fromRectAndRadius(
      Rect.fromLTWH(0, alto / 2 - 3, medida.width, 6),
      const Radius.circular(3),
    );
    lienzo.drawRRect(fondo, Paint()..color = AppColors.outlineVariant);

    final double ini = _x(min, medida.width);
    final double fin = _x(max, medida.width);
    lienzo.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTRB(ini, alto / 2 - 3, fin, alto / 2 + 3),
        const Radius.circular(3),
      ),
      Paint()..color = AppColors.exito.withValues(alpha: 0.45),
    );

    final double x = _x(dbm, medida.width);
    lienzo.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(x - 1.5, 0, 3, alto),
        const Radius.circular(2),
      ),
      Paint()..color = marca,
    );
  }

  @override
  bool shouldRepaint(covariant _ReglaOptica anterior) =>
      anterior.dbm != dbm || anterior.marca != marca;
}
