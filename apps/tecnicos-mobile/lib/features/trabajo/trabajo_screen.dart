import 'package:flutter/material.dart';

import '../../core/estado/ordenes_jornada.dart';
import '../../core/mock/field_mock_data.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_empty_state.dart';
import '../../core/widgets/dexter_metric_tile.dart';
import 'estado_trabajo.dart';
import 'seleccion_jornada.dart';
import 'trabajo_vista.dart';
import 'widgets/tarjeta_trabajo.dart';

/// La lista de trabajos del técnico.
///
/// Las órdenes no las carga esta pantalla: las comparte con Inicio a través de
/// [OrdenesJornada]. Acá viven solo las decisiones de esta pantalla — qué
/// pestaña está elegida, qué filtro, y dónde quedó el scroll.
class TrabajoScreen extends StatefulWidget {
  const TrabajoScreen({
    super.key,
    required this.ordenes,
    required this.abrirTrabajo,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
  });

  final OrdenesJornada ordenes;

  /// Abre el trabajo y devuelve el control cuando el técnico vuelve.
  final Future<void> Function(BuildContext contexto, TrabajoVista trabajo) abrirTrabajo;

  final bool mostrarDatosFuturos;

  @override
  State<TrabajoScreen> createState() => _TrabajoScreenState();
}

class _TrabajoScreenState extends State<TrabajoScreen> {
  PestanaTrabajo _pestana = PestanaTrabajo.hoy;
  FamiliaTrabajo? _familia;

  @override
  void initState() {
    super.initState();
    widget.ordenes.addListener(_alCambiar);
    // La primera pantalla que se abre dispara la carga; la segunda encuentra
    // los datos ya cargados.
    widget.ordenes.asegurarCargado();
  }

  @override
  void dispose() {
    widget.ordenes.removeListener(_alCambiar);
    super.dispose();
  }

  void _alCambiar() {
    if (mounted) setState(() {});
  }

  List<TrabajoVista> _deLaPestana(PestanaTrabajo pestana) {
    final ahora = DateTime.now();
    return widget.ordenes.trabajos
        .where((TrabajoVista t) =>
            perteneceA(pestana, t.estado, t.compromiso, ahora: ahora))
        .where((TrabajoVista t) => _familia == null || t.familia == _familia)
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.ordenes.cargando) {
      return const ColoredBox(
        color: AppColors.fondo,
        child: Center(child: CircularProgressIndicator()),
      );
    }

    final visibles = _deLaPestana(_pestana);

    return ColoredBox(
      color: AppColors.fondo,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _resumen(),
          _pestanas(),
          _filtros(),
          Expanded(
            child: RefreshIndicator(
              onRefresh: widget.ordenes.refrescar,
              child: widget.ordenes.fallo
                  ? ListView(
                      children: const <Widget>[
                        SizedBox(height: AppSpacing.xl),
                        DexterEmptyState(
                          icono: Icons.error_outline,
                          titulo: 'No se pudieron leer tus trabajos',
                          mensaje: 'Deslizá hacia abajo para volver a intentar.',
                          esAdvertencia: true,
                        ),
                      ],
                    )
                  : visibles.isEmpty
                      ? ListView(
                          children: <Widget>[
                            const SizedBox(height: AppSpacing.xl),
                            DexterEmptyState(
                              icono: _iconoVacio,
                              titulo: _tituloVacio,
                              mensaje: _mensajeVacio,
                            ),
                          ],
                        )
                      : ListView.builder(
                          key: PageStorageKey<String>('trabajos_${_pestana.name}'),
                          padding: const EdgeInsets.fromLTRB(
                            AppSpacing.margen,
                            AppSpacing.md,
                            AppSpacing.margen,
                            AppSpacing.xl,
                          ),
                          itemCount: visibles.length,
                          itemBuilder: (BuildContext contexto, int i) {
                            final trabajo = visibles[i];
                            return TarjetaTrabajo(
                              trabajo: trabajo,
                              mostrarDatosFuturos: widget.mostrarDatosFuturos,
                              onTap: () async {
                                await widget.abrirTrabajo(contexto, trabajo);
                                // Al volver, los datos pueden haber cambiado;
                                // la pestaña, el filtro y el scroll no.
                                await widget.ordenes.recargar();
                              },
                            );
                          },
                        ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _resumen() {
    final trabajos = widget.ordenes.trabajos;
    final activos = SeleccionJornada.activos(trabajos).length;
    final enMarcha = SeleccionJornada.enCurso(trabajos).length;
    final terminados = SeleccionJornada.terminados(trabajos).length;

    return Container(
      color: AppColors.superficie,
      padding: const EdgeInsets.all(AppSpacing.margen),
      child: Row(
        children: <Widget>[
          Expanded(
            child: DexterMetricTile(
              etiqueta: 'Te quedan',
              valor: '$activos',
              icono: Icons.assignment_outlined,
              compacto: true,
              tono: activos == 0 ? DexterMetricTone.exito : DexterMetricTone.neutro,
            ),
          ),
          Expanded(
            child: DexterMetricTile(
              etiqueta: 'En proceso',
              valor: '$enMarcha',
              icono: Icons.play_arrow,
              compacto: true,
              tono: DexterMetricTone.info,
            ),
          ),
          Expanded(
            child: DexterMetricTile(
              etiqueta: 'Terminados',
              valor: '$terminados de ${trabajos.length}',
              icono: Icons.check_circle_outline,
              compacto: true,
              tono: DexterMetricTone.exito,
            ),
          ),
        ],
      ),
    );
  }

  Widget _pestanas() {
    final ahora = DateTime.now();
    return Container(
      color: AppColors.superficie,
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.margen),
        child: Row(
          children: <Widget>[
            for (final PestanaTrabajo pestana in PestanaTrabajo.values)
              Padding(
                padding: const EdgeInsets.only(right: AppSpacing.sm),
                child: _Pestana(
                  texto: pestana.etiqueta,
                  cantidad: widget.ordenes.trabajos
                      .where((TrabajoVista t) =>
                          perteneceA(pestana, t.estado, t.compromiso, ahora: ahora))
                      .length,
                  activa: pestana == _pestana,
                  onTap: () => setState(() => _pestana = pestana),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _filtros() {
    // Familias que de verdad hay entre los trabajos descargados. Si el técnico
    // solo tiene instalaciones, no aparece un filtro de incidencias vacío.
    final presentes = <FamiliaTrabajo>{
      for (final TrabajoVista t in widget.ordenes.trabajos) t.familia,
    }.toList();

    return Container(
      decoration: const BoxDecoration(
        color: AppColors.superficie,
        border: Border(bottom: BorderSide(color: AppColors.borde)),
      ),
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.margen,
        0,
        AppSpacing.margen,
        AppSpacing.sm,
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: <Widget>[
            _ChipFiltro(
              texto: 'Todos',
              activo: _familia == null,
              onTap: () => setState(() => _familia = null),
            ),
            for (final FamiliaTrabajo familia in presentes) ...<Widget>[
              const SizedBox(width: AppSpacing.sm),
              _ChipFiltro(
                texto: familia.etiqueta,
                activo: _familia == familia,
                onTap: () => setState(() => _familia = familia),
              ),
            ],
            const SizedBox(width: AppSpacing.md),
            // CAMPO-DATA-003 y CAMPO-DATA-004: los dos filtros que el diseño
            // muestra y todavía no se pueden aplicar, porque la orden no trae
            // zona ni prioridad. Se ven apagados y no se pueden tocar — un
            // filtro que parece andar y no filtra es peor que no tenerlo.
            const _ChipPendiente(texto: 'Zona'),
            const SizedBox(width: AppSpacing.sm),
            const _ChipPendiente(texto: 'Prioridad'),
          ],
        ),
      ),
    );
  }

  IconData get _iconoVacio => switch (_pestana) {
        PestanaTrabajo.hoy => Icons.event_available,
        PestanaTrabajo.pendientes => Icons.inbox_outlined,
        PestanaTrabajo.enProceso => Icons.play_circle_outline,
        PestanaTrabajo.finalizadas => Icons.done_all,
      };

  String get _tituloVacio => switch (_pestana) {
        PestanaTrabajo.hoy => 'No tenés trabajos para hoy',
        PestanaTrabajo.pendientes => 'No tenés trabajos pendientes',
        PestanaTrabajo.enProceso => 'No tenés ningún trabajo empezado',
        PestanaTrabajo.finalizadas => 'Todavía no terminaste ninguno',
      };

  String? get _mensajeVacio {
    if (_familia != null) {
      return 'Con el filtro "${_familia!.etiqueta}" no hay nada acá. '
          'Probá con Todos.';
    }
    return switch (_pestana) {
      PestanaTrabajo.hoy =>
        'Acá aparecen los que tienen fecha para hoy. Deslizá para actualizar.',
      PestanaTrabajo.pendientes => 'Deslizá hacia abajo para actualizar.',
      PestanaTrabajo.enProceso =>
        'Cuando marques que vas en camino, el trabajo aparece acá.',
      PestanaTrabajo.finalizadas => null,
    };
  }
}

class _Pestana extends StatelessWidget {
  const _Pestana({
    required this.texto,
    required this.cantidad,
    required this.activa,
    required this.onTap,
  });

  final String texto;
  final int cantidad;
  final bool activa;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = activa ? AppColors.azulMarino : AppColors.textoSecundario;

    return Semantics(
      button: true,
      selected: activa,
      label: '$texto, $cantidad',
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: AppRadius.brCampo,
        child: Container(
          constraints: const BoxConstraints(minHeight: AppSpacing.objetivoTactil),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
          decoration: BoxDecoration(
            color: activa ? AppColors.fondoHundido : AppColors.superficie,
            borderRadius: AppRadius.brCampo,
            border: Border.all(color: activa ? AppColors.azulMarino : AppColors.borde),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(
                texto,
                style: AppTypography.cuerpoGrande.copyWith(
                  color: color,
                  fontWeight: activa ? FontWeight.w600 : FontWeight.w500,
                ),
              ),
              const SizedBox(width: AppSpacing.xs),
              Text(
                '$cantidad',
                style: AppTypography.etiqueta.copyWith(color: color),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ChipFiltro extends StatelessWidget {
  const _ChipFiltro({
    required this.texto,
    required this.activo,
    required this.onTap,
  });

  final String texto;
  final bool activo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: activo,
      label: 'Filtrar por $texto',
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: AppRadius.brChico,
        child: Container(
          constraints: const BoxConstraints(minHeight: AppSpacing.objetivoTactil),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
          decoration: BoxDecoration(
            color: activo ? AppColors.azulMarino : AppColors.superficie,
            borderRadius: AppRadius.brChico,
            border: Border.all(color: activo ? AppColors.azulMarino : AppColors.borde),
          ),
          child: Text(
            texto,
            style: AppTypography.etiqueta.copyWith(
              color: activo ? AppColors.textoSobreOscuro : AppColors.texto,
            ),
          ),
        ),
      ),
    );
  }
}

/// Filtro del diseño que todavía no se puede aplicar.
class _ChipPendiente extends StatelessWidget {
  const _ChipPendiente({required this.texto});

  final String texto;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '$texto: filtro todavía no disponible',
      excludeSemantics: true,
      child: Container(
        constraints: const BoxConstraints(minHeight: AppSpacing.objetivoTactil),
        alignment: Alignment.center,
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.fondoHundido,
          borderRadius: AppRadius.brChico,
          border: Border.all(color: AppColors.borde),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Icon(Icons.lock_outline, size: 13, color: AppColors.inactivo),
            const SizedBox(width: AppSpacing.xs),
            Text(
              texto,
              style: AppTypography.etiqueta.copyWith(color: AppColors.inactivo),
            ),
            const SizedBox(width: AppSpacing.xs),
            Text(
              'PRONTO',
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.inactivo,
                fontSize: 9,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
