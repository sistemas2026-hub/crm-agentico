import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/estado/ordenes_jornada.dart';
import '../../core/mock/field_mock_data.dart';
import '../../core/sync/sync_presentacion.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_card.dart';
import '../../core/widgets/dexter_empty_state.dart';
import '../../core/widgets/dexter_metric_tile.dart';
import '../../core/widgets/dexter_status_badge.dart';
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
  final Future<void> Function(BuildContext contexto, TrabajoVista trabajo)? abrirEjecucion;

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
    _suscripcionResumen = widget.resumenes?.listen(
      (SyncSummary resumen) {
        if (mounted) setState(() => _resumen = resumen);
      },
      onError: (Object _) {},
    );
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
      BuildContext contexto, TrabajoVista trabajo) async {
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
        appBar: AppBar(title: const Text('Orden')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    if (trabajo == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Orden')),
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
          trabajo.numero == null ? 'Orden' : 'Orden #${trabajo.numero}',
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
      body: ListView(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.margen,
          AppSpacing.lg,
          AppSpacing.margen,
          AppSpacing.xl,
        ),
        children: <Widget>[
          if (trabajo.requiereActualizacion) _avisoActualizacion(),
          _cabecera(trabajo),
          const SizedBox(height: AppSpacing.md),
          _BarraDePasos(lectura: lectura),
          if (lectura.avisoExcepcion != null) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            _avisoExcepcion(trabajo, lectura),
          ],
          if (trabajo.estado == EstadoTrabajo.completadaSinEnviar) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            _avisoSinEnviar(),
          ],
          const SizedBox(height: AppSpacing.md),
          _datosDelCliente(trabajo),
          if (trabajo.diagnosticoPrevio.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            _diagnostico(trabajo),
          ],
          if (widget.mostrarDatosFuturos) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            _telemetria(trabajo),
          ],
          const SizedBox(height: AppSpacing.lg),
          _acciones(trabajo, acciones),
        ],
      ),
    );
  }

  Widget _avisoActualizacion() {
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
                'Esta orden necesita una versión más nueva de la aplicación. '
                'Actualizala antes de trabajarla.',
                style: AppTypography.cuerpo.copyWith(color: AppColors.error),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _cabecera(TrabajoVista trabajo) {
    return DexterCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  trabajo.tipoNombre.toUpperCase(),
                  style: AppTypography.etiquetaChica.copyWith(
                    color: AppColors.azulMarino,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              DexterStatusBadge(
                estado: trabajo.estado.presentacion,
                etiqueta: trabajo.estado.etiqueta,
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(trabajo.clienteNombre, style: AppTypography.tituloMedio),
          if (trabajo.compromiso != null) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Comprometido para ${_fechaYHora(trabajo.compromiso!)}',
              style: AppTypography.etiqueta,
            ),
          ],
        ],
      ),
    );
  }

  Widget _datosDelCliente(TrabajoVista trabajo) {
    return DexterCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('DATOS DEL CLIENTE', style: AppTypography.etiquetaChica),
          const SizedBox(height: AppSpacing.sm),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Icon(Icons.location_on_outlined,
                  size: 16, color: AppColors.azulAccion),
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
                const Icon(Icons.phone_outlined, size: 16, color: AppColors.exito),
                const SizedBox(width: AppSpacing.sm),
                Text(
                  trabajo.telefono,
                  style: AppTypography.etiquetaGrande,
                ),
              ],
            ),
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

  Widget _diagnostico(TrabajoVista trabajo) {
    return DexterCard(
      colorAcento: AppColors.azulAccion,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.auto_awesome, size: 16, color: AppColors.azulAccion),
              const SizedBox(width: AppSpacing.xs),
              Text(
                'DIAGNÓSTICO PREVIO',
                style: AppTypography.etiquetaChica.copyWith(
                  color: AppColors.azulAccion,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          // Tal cual llega. No se parte en checks ni en causas: el backend
          // manda un texto, no campos estructurados, y fabricar la estructura
          // sería inventar un diagnóstico que nadie hizo.
          Text(trabajo.diagnosticoPrevio, style: AppTypography.cuerpo),
        ],
      ),
    );
  }

  /// CAMPO-DATA-001 y CAMPO-DATA-011. Ningún sistema entrega esto para campo
  /// todavía; se ve solo en modo demostración.
  Widget _telemetria(TrabajoVista trabajo) {
    return DexterCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('SEÑAL DEL CLIENTE', style: AppTypography.etiquetaChica),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: <Widget>[
              Expanded(
                child: DexterMetricTile(
                  etiqueta: 'Potencia RX',
                  valor: trabajo.futuro.potenciaRxDbm.toStringAsFixed(1),
                  unidad: 'dBm',
                  tono: DexterMetricTone.precaucion,
                  nota: 'Rango aceptable: -8 a -25',
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text('CTO ${FieldMockData.cto}', style: AppTypography.etiqueta),
                    const SizedBox(height: AppSpacing.xs),
                    Text(FieldMockData.puertoPon, style: AppTypography.etiqueta),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      'ONT ${FieldMockData.serialOnt}',
                      style: AppTypography.etiquetaChica,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _avisoExcepcion(TrabajoVista trabajo, LecturaDePasos lectura) {
    final esCancelada = trabajo.estado == EstadoTrabajo.cancelada;
    return DexterCard(
      colorFondo: esCancelada ? AppColors.inactivoFondo : AppColors.precaucionFondo,
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
              const Icon(Icons.cloud_upload_outlined,
                  size: 18, color: AppColors.precaucion),
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
          onPressed:
              _trabajando ? null : () => _ejecutarAccion(trabajo, acciones.primaria!),
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
            onPressed: _trabajando ? null : () => _ejecutarAccion(trabajo, secundaria),
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

  static String _fechaYHora(DateTime fecha) {
    final dd = fecha.day.toString().padLeft(2, '0');
    final mm = fecha.month.toString().padLeft(2, '0');
    final hh = fecha.hour.toString().padLeft(2, '0');
    final min = fecha.minute.toString().padLeft(2, '0');
    return '$dd/$mm a las $hh:$min';
  }
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
          Text(
            lectura.pasoActual < 0
                ? 'Sin avance'
                : 'Paso ${lectura.pasoActual + 1} de ${PasoOrden.values.length}: '
                    '${PasoOrden.values[lectura.pasoActual].etiqueta}',
            style: AppTypography.etiquetaChica,
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
