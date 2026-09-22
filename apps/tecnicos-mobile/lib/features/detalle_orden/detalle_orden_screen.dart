import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/estado/ordenes_jornada.dart';
import '../../core/mock/field_mock_data.dart';
import '../../core/mock/kit_mock_data.dart';
import '../../core/sync/sync_presentacion.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_card.dart';
import '../../core/widgets/dexter_empty_state.dart';
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

class _DetalleOrdenScreenState extends State<DetalleOrdenScreen> {
  StreamSubscription<SyncSummary>? _suscripcionResumen;
  SyncSummary? _resumen;
  bool _trabajando = false;

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
          trabajo.numero == null ? 'Detalle Orden' : 'Detalle Orden #${trabajo.numero}',
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
      body: Column(
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
                if (widget.mostrarDatosFuturos) ...<Widget>[
                  const SizedBox(height: AppSpacing.md),
                  _trazabilidadYOrigen(trabajo),
                ],
                if (widget.mostrarDatosFuturos) ...<Widget>[
                  const SizedBox(height: AppSpacing.md),
                  _telemetria(trabajo),
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
          Text(
            FieldMockData.enlaceDexter,
            style: AppTypography.etiquetaChica.copyWith(
              color: AppColors.inverseOnSurface,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          const Icon(Icons.check, size: 12, color: AppColors.exitoFuerte),
          const SizedBox(width: 2),
          Text(
            'En dispositivo',
            style: AppTypography.etiquetaChica.copyWith(
              color: AppColors.exitoFuerte,
            ),
          ),
          const Spacer(),
          const Icon(Icons.cloud_done, size: 14, color: AppColors.surfaceDim),
          const SizedBox(width: 4),
          Text(
            'Sync: ${FieldMockData.ultimaSincronizacion}',
            style: AppTypography.etiquetaChica.copyWith(
              color: AppColors.surfaceDim,
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
                    'SLA ${trabajo.futuro.slaRestante}h',
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

  /// CAMPO-DATA-029 y CAMPO-DATA-047 · De dónde vino la orden.
  ///
  /// La cita del abonado —si la hay— es real: es `diagnostico_previo_ia`. Lo
  /// que todavía no existe es el rastro del ticket y de quién lo abrió.
  Widget _trazabilidadYOrigen(TrabajoVista trabajo) {
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
              const Icon(Icons.alt_route, size: 16, color: AppColors.secondary),
              const SizedBox(width: 6),
              Text(
                'Origen NOC',
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.onSurface,
                ),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: const BoxDecoration(
                  color: AppColors.surfaceContainer,
                  borderRadius: AppRadius.brChico,
                ),
                child: Text(
                  trabajo.origen?.etiqueta ?? trabajo.futuro.ticketOrigen,
                  style: AppTypography.datoChico,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            FieldMockData.origenApertura,
            style: AppTypography.etiquetaChica,
          ),
          if (trabajo.diagnosticoPrevio.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Text(
              'Reporte del Abonado',
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.onSurface,
                fontWeight: FontWeight.w700,
              ),
            ),
            Text(
              '“${trabajo.diagnosticoPrevio}”',
              style: AppTypography.cuerpoChico.copyWith(
                fontStyle: FontStyle.italic,
                color: AppColors.onSurface,
              ),
            ),
          ],
        ],
      ),
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
          const SizedBox(height: AppSpacing.sm),
          _ubicacion(trabajo),
          if (widget.mostrarDatosFuturos) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            // CAMPO-DATA-023 · El plan que tiene contratado el cliente.
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
                    'Zona ${trabajo.zona.isEmpty ? trabajo.futuro.zona : trabajo.zona}',
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
  String get _plan {
    final String real = _trabajo?.planContratado ?? '';
    return real.isEmpty ? 'Fibra 500 Mbps Simétrica' : real;
  }

  /// CAMPO-DATA-023 · Qué tiene contratado el cliente.
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
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: const BoxDecoration(
              color: AppColors.secondaryFixed,
              borderRadius: AppRadius.brChico,
            ),
            child: Text(
              '+ Dexter TV',
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.onSecondaryContainer,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// CAMPO-DATA-001, 011 y 012: telemetría de red. Ningún sistema la entrega
  /// para campo todavía; se ve solo en modo demostración.
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
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                decoration: const BoxDecoration(
                  color: AppColors.surfaceContainerHigh,
                  borderRadius: AppRadius.brChico,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Container(
                      width: 6,
                      height: 6,
                      decoration: const BoxDecoration(
                        color: AppColors.exitoFuerte,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 4),
                    Text('Live', style: AppTypography.etiquetaChica),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          Row(
            children: <Widget>[
              Expanded(
                child: _CajaDato(
                  titulo: 'ONT SERIAL',
                  valor: FieldMockData.serialOnt,
                  detalle: 'Huawei HG8145V5',
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: _CajaDato(
                  titulo: 'PUERTO PON / CTO',
                  valor: FieldMockData.puertoPon,
                  detalle: FieldMockData.terminal,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Container(
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
                      style: AppTypography.medicion.copyWith(
                        color: AppColors.error,
                      ),
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
          ),
          const SizedBox(height: AppSpacing.sm),
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
          const SizedBox(height: AppSpacing.xs),
          Text(
            FieldMockData.fuenteTelemetria,
            style: AppTypography.etiquetaChica.copyWith(
              color: AppColors.outline,
              fontSize: 10,
            ),
          ),
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
