import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../demo/field_mock_data.dart';
import '../../demo/kit_mock_data.dart';
import '../../core/storage/local_database.dart';
import 'kit_de_jornada.dart';
import 'material_en_custodia.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_empty_state.dart';

/// Materiales — Mi kit y custodia.
///
/// Réplica de la pantalla del diseño: la recepción del kit, la trazabilidad,
/// las cifras del día, la barra de acciones, los filtros por categoría, la
/// lista de materiales en custodia y el cierre de jornada.
///
/// DE DONDE SALEN ESTOS DATOS
/// --------------------------
/// De la base del telefono: `local_kit` es lo que dijo el servidor la ultima
/// vez que hubo senal, y la cola de movimientos es lo que paso despues. El
/// saldo que se ve son las dos cosas sumadas al leer, nunca un numero
/// guardado -- asi el tecnico ve el descuento apenas registra el consumo,
/// este o no conectado.
///
/// El catalogo de ejemplo sigue existiendo, pero solo se dibuja con el modo
/// demostracion encendido Y sin una jornada cargada: sirve para ensenar la
/// aplicacion, no para tapar un kit vacio. Si hay kit real, gana el real.
class MaterialesScreen extends StatefulWidget {
  const MaterialesScreen({
    super.key,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
    this.tecnico,
    this.kit,
  });

  final bool mostrarDatosFuturos;

  /// El kit ya leido. Se inyecta en las pruebas; en la aplicacion se lee solo.
  final KitDeJornada? kit;

  /// Quién tiene el kit a cargo. Es la sesión real: el kit es de ejemplo, pero
  /// el nombre de quien firmaría la recepción no se inventa.
  final String? tecnico;

  @override
  State<MaterialesScreen> createState() => _MaterialesScreenState();
}

class _MaterialesScreenState extends State<MaterialesScreen> {
  _Categoria _categoria = _Categoria.todos;

  StreamSubscription<LocalDatabaseChangeEvent>? _suscripcion;
  KitDeJornada? _kit;
  bool _cargando = true;

  @override
  void dispose() {
    _suscripcion?.cancel();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _cargar();
    // La pantalla se refresca sola cuando la cola cambia: registrar un
    // consumo desde una orden tiene que verse aca sin volver a entrar.
    // La suscripcion se guarda para poder cancelarla en dispose.
    //
    // Sin eso queda viva despues de que la pantalla se fue: es una fuga en el
    // telefono, y en una prueba deja al arbol con un oyente pendiente que
    // impide que el test termine.
    _suscripcion = LocalDatabase.onDataChanged.listen((evento) {
      if (!mounted) return;
      if (evento.tabla == 'local_kit' ||
          evento.tabla == 'cola_movimientos_material') {
        _cargar();
      }
    });
  }

  Future<void> _cargar() async {
    if (widget.kit != null) {
      setState(() {
        _kit = widget.kit;
        _cargando = false;
      });
      return;
    }
    final kit = await KitDeJornada.leer();
    if (!mounted) return;
    setState(() {
      _kit = kit;
      _cargando = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_cargando) {
      // Un fondo quieto, no un indicador que gira.
      //
      // Esto lee SQLite: son milisegundos, y un spinner para eso solo hace
      // parpadear la pantalla. Ademas una animacion perpetua deja a la
      // pantalla sin "reposo", que es lo que rompe cualquier prueba que
      // espere a que las animaciones terminen.
      return const ColoredBox(color: AppColors.surface);
    }

    final kit = _kit ?? const KitDeJornada.vacio();

    // Lo real le gana al ejemplo: el catalogo de demostracion solo aparece
    // cuando NO hay kit cargado, para poder ensenar la pantalla.
    final List<MaterialEnCustodia> todos =
        kit.hayAlgo ? kit.materiales : (widget.mostrarDatosFuturos
            ? KitMockData.items
            : const <MaterialEnCustodia>[]);

    if (todos.isEmpty) {
      return const ColoredBox(
        color: AppColors.surface,
        child: Center(
          child: DexterEmptyState(
            icono: Icons.inventory_2_outlined,
            titulo: 'Mi kit y custodia',
            mensaje: 'Todavía no hay material entregado a tu nombre. Aparece '
                'cuando la bodega registre la entrega y haya señal para '
                'sincronizar.',
          ),
        ),
      );
    }

    final visibles = _categoria == _Categoria.todos
        ? todos
        : todos.where((MaterialEnCustodia m) => _categoria.incluye(m)).toList();

    return ColoredBox(
      color: AppColors.surface,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.margen,
          AppSpacing.md,
          AppSpacing.margen,
          AppSpacing.xl,
        ),
        children: <Widget>[
          Text('Mi Kit', style: AppTypography.tituloGrande),
          Text(
            'Material bajo tu custodia para la jornada de hoy',
            style: AppTypography.cuerpoChico,
          ),
          const SizedBox(height: AppSpacing.md),
          _recepcionDelKit(todos),
          const SizedBox(height: AppSpacing.md),
          _barraDeAcciones(),
          const SizedBox(height: AppSpacing.md),
          _filtros(todos),
          const SizedBox(height: AppSpacing.md),
          Row(
            children: <Widget>[
              Text('Materiales en Custodia', style: AppTypography.tituloChico),
              const Spacer(),
              // Cuántos renglones hay, que es lo que sí se sabe. La fecha de
              // la jornada no viaja en el kit.
              Text(
                todos.length == 1 ? '1 material' : '${todos.length} materiales',
                style: AppTypography.etiquetaChica,
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          for (final MaterialEnCustodia material in visibles)
            _TarjetaMaterial(material: material),
          const SizedBox(height: AppSpacing.sm),
          _cierreDeJornada(),
          const SizedBox(height: AppSpacing.md),
          _selloDeAuditoria(),
        ],
      ),
    );
  }

  // --- Recepción del kit ---------------------------------------------------

  /// Con qué acta llegó este kit y cómo va.
  ///
  /// LO QUE SE FUE DE ACÁ
  /// --------------------
  /// El depósito de origen, quién despachó, la hora del despacho y la del
  /// acuse. Nada de eso viaja en el kit: eran constantes de ejemplo, y con un
  /// kit real quedaban alrededor de la lista verdadera, indistinguibles. El
  /// acta inventada era la peor: **tapaba la real**, así que el técnico veía
  /// un número de acta que no era el suyo.
  ///
  /// Las cuatro cifras se suman sobre los renglones que esta misma pantalla
  /// está mostrando. No es una segunda cuenta del saldo —ese ya lo hizo
  /// `KitDeJornada` mezclando lo del servidor con la cola—: es el total de lo
  /// que se ve abajo, y por eso no puede contradecirlo.
  Widget _recepcionDelKit(List<MaterialEnCustodia> materiales) {
    var recibidos = 0;
    var usados = 0;
    for (final MaterialEnCustodia m in materiales) {
      recibidos += m.recibidos;
      usados += m.usados;
    }
    final int novedades = _kit?.conNovedad.length ?? 0;
    final String acta = _kit?.acta ?? '';

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
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      'Mi Kit Diario',
                      style: AppTypography.tituloMedio.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (widget.tecnico != null)
                      Text(
                        'A cargo de ${widget.tecnico}',
                        style: AppTypography.cuerpoChico,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    // El acta sólo si el servidor la mandó: sin ella no se
                    // escribe un número, porque es el que alguien va a citar
                    // cuando falte material.
                    if (acta.isNotEmpty) ...<Widget>[
                      const SizedBox(height: 2),
                      Text(
                        acta,
                        style: AppTypography.datoChico.copyWith(
                          color: AppColors.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              Container(
                width: 48,
                height: 48,
                decoration: const BoxDecoration(
                  color: AppColors.surfaceContainer,
                  borderRadius: AppRadius.brTarjeta,
                ),
                child: const Icon(Icons.inventory, size: 24, color: AppColors.primary),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          Row(
            children: <Widget>[
              Expanded(
                child: _Cifra(valor: '$recibidos', etiqueta: 'Recibidos'),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: _Cifra(
                  valor: '$usados',
                  etiqueta: 'Consumo',
                  color: AppColors.secondary,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: _Cifra(
                  valor: '${recibidos - usados}',
                  etiqueta: 'Disponibles',
                  destacada: true,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: _Cifra(
                  valor: '$novedades',
                  etiqueta: 'Novedades',
                  color: novedades == 0 ? AppColors.exito : AppColors.error,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Cuánto queda por devolver, contado sobre el kit que se está mostrando.
  ///
  /// Antes decía un número fijo. Alguien con tres conectores encima leía que
  /// tenía dieciséis listos para conciliar, y ese es justo el momento en que
  /// la cuenta importa.
  String _fraseDeCierre() {
    final List<MaterialEnCustodia> materiales =
        _kit?.materiales ?? const <MaterialEnCustodia>[];
    var disponibles = 0;
    for (final MaterialEnCustodia m in materiales) {
      disponibles += m.disponibles;
    }
    if (disponibles == 0) {
      return 'No te queda material por devolver a la bodega.';
    }
    return disponibles == 1
        ? 'Te queda 1 material disponible para conciliar y devolver a bodega.'
        : 'Te quedan $disponibles materiales disponibles para conciliar y '
            'devolver a bodega.';
  }

  Widget _barraDeAcciones() {
    return Row(
      children: <Widget>[
        const Expanded(
          child: _BotonHerramienta(
            icono: Icons.qr_code_scanner,
            texto: 'Escanear QR',
            principal: true,
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        const Expanded(
          child: _BotonHerramienta(
            icono: Icons.sync_alt,
            texto: 'Transferir',
            colorIcono: AppColors.secondary,
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        const Expanded(
          child: _BotonHerramienta(
            icono: Icons.report_problem,
            texto: 'Incidencia',
            colorIcono: AppColors.error,
          ),
        ),
      ],
    );
  }

  /// El diseño separa en dos lo que el técnico tiene a cargo: lo que hay que
  /// rastrear uno por uno (serializados) y lo que se gasta. Las bobinas y las
  /// terminales entran en lo segundo.
  Widget _filtros(List<MaterialEnCustodia> todos) {
    // Se cuenta lo que hay, no el catálogo de ejemplo: con un kit real de un
    // renglón, los filtros anunciaban "Todos (5)".
    int cuantos(_Categoria categoria) =>
        todos.where((MaterialEnCustodia m) => categoria.incluye(m)).length;

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: <Widget>[
          for (final _Categoria categoria in _Categoria.values) ...<Widget>[
            if (categoria != _Categoria.values.first)
              const SizedBox(width: AppSpacing.sm),
            _ChipCategoria(
              texto: '${categoria.etiqueta} (${cuantos(categoria)})',
              activo: _categoria == categoria,
              punto: categoria.punto,
              onTap: () => setState(() => _categoria = categoria),
            ),
          ],
        ],
      ),
    );
  }

  // --- Cierre de jornada ---------------------------------------------------

  Widget _cierreDeJornada() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: <Color>[AppColors.primary, AppColors.primaryContainer],
        ),
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel2,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: AppColors.onPrimary.withValues(alpha: 0.12),
                  borderRadius: AppRadius.brTarjeta,
                ),
                child: const Icon(Icons.assignment_turned_in,
                    size: 24, color: AppColors.exitoFuerte),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: const BoxDecoration(
                        color: AppColors.exito,
                        borderRadius: AppRadius.brChico,
                      ),
                      child: Text(
                        'CIERRE OPERATIVO',
                        style: AppTypography.etiquetaChica.copyWith(
                          color: AppColors.onPrimary,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      'PASO PREVIO AL CIERRE',
                      style: AppTypography.etiquetaChica.copyWith(
                        color: AppColors.primaryFixedDim,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      '¿Finalizaste tu turno?',
                      style: AppTypography.tituloMedio.copyWith(
                        color: AppColors.onPrimary,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      _fraseDeCierre(),
                      style: AppTypography.cuerpoChico.copyWith(
                        color: AppColors.primaryFixed,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: AppSpacing.md),
          Container(
            height: 54,
            alignment: Alignment.center,
            decoration: const BoxDecoration(
              color: AppColors.surfaceBright,
              borderRadius: AppRadius.brTarjeta,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                const Icon(Icons.keyboard_return, size: 18, color: AppColors.primary),
                const SizedBox(width: AppSpacing.sm),
                Text(
                  'Preparar Devolución al Depósito',
                  style: AppTypography.etiquetaGrande.copyWith(
                    color: AppColors.primary,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                const Icon(Icons.arrow_forward, size: 18, color: AppColors.primary),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
        ],
      ),
    );
  }

  /// El sello queda fuera de la tarjeta, como una nota al pie del módulo.
  Widget _selloDeAuditoria() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        const Icon(Icons.lock_outline, size: 12, color: AppColors.outline),
        const SizedBox(width: 4),
        Flexible(
          child: Text(
            'Trazabilidad auditada · Dexter Field',
            textAlign: TextAlign.center,
            style: AppTypography.etiquetaChica,
          ),
        ),
      ],
    );
  }
}

class _Cifra extends StatelessWidget {
  const _Cifra({
    required this.valor,
    required this.etiqueta,
    this.destacada = false,
    this.color,
  });

  final String valor;
  final String etiqueta;
  final bool destacada;

  /// Con qué color se lee la cifra. El diseño distingue lo consumido de lo
  /// disponible y de las incidencias: son tres lecturas distintas.
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      decoration: BoxDecoration(
        color: destacada
            ? AppColors.surfaceContainerHigh
            : AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brCampo,
      ),
      child: Column(
        children: <Widget>[
          Text(
            valor,
            style: AppTypography.tituloMedio.copyWith(
              fontFamily: AppTypography.familiaMono,
              fontWeight: FontWeight.w700,
              color: color ?? (destacada ? AppColors.primary : AppColors.onSurface),
            ),
          ),
          Text(
            etiqueta,
            style: AppTypography.etiquetaChica,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

class _BotonHerramienta extends StatelessWidget {
  const _BotonHerramienta({
    required this.icono,
    required this.texto,
    this.principal = false,
    this.colorIcono,
  });

  final IconData icono;
  final String texto;
  final bool principal;
  final Color? colorIcono;

  @override
  Widget build(BuildContext context) {
    final color = principal ? AppColors.onPrimary : AppColors.onSurface;
    return Container(
      constraints: const BoxConstraints(minHeight: 52),
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      decoration: BoxDecoration(
        color: principal ? AppColors.primary : AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          Icon(icono, size: 20, color: principal ? color : (colorIcono ?? color)),
          const SizedBox(height: 2),
          Text(
            texto,
            style: AppTypography.etiquetaChica.copyWith(color: color),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

class _ChipCategoria extends StatelessWidget {
  const _ChipCategoria({
    required this.texto,
    required this.activo,
    required this.onTap,
    this.punto,
  });

  final String texto;
  final bool activo;
  final VoidCallback onTap;
  final Color? punto;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(AppRadius.circulo),
      child: Container(
        height: 40,
        alignment: Alignment.center,
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
        decoration: BoxDecoration(
          color: activo ? AppColors.primary : AppColors.surfaceContainerLowest,
          borderRadius: BorderRadius.circular(AppRadius.circulo),
          boxShadow: AppTheme.sombraNivel1,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            if (punto != null && !activo) ...<Widget>[
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(color: punto, shape: BoxShape.circle),
              ),
              const SizedBox(width: 6),
            ],
            Text(
              texto,
              style: AppTypography.etiquetaChica.copyWith(
                color: activo ? AppColors.onPrimary : AppColors.onSurfaceVariant,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Una tarjeta de material, con la forma que le corresponde a su clase.
class _TarjetaMaterial extends StatelessWidget {
  const _TarjetaMaterial({required this.material});

  final MaterialEnCustodia material;

  /// El diseño colorea la categoría según de qué se trate: verde lo que se
  /// consume, azul lo que se mide y se fracciona.
  Color get _colorDeClase => switch (material.clase) {
        ClaseMaterial.consumible => AppColors.exito,
        ClaseMaterial.bobina => AppColors.secondary,
        ClaseMaterial.terminal => AppColors.onSurfaceVariant,
        ClaseMaterial.serializado => AppColors.secondary,
      };

  @override
  Widget build(BuildContext context) {
    final serializado = material.clase == ClaseMaterial.serializado;

    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      clipBehavior: Clip.antiAlias,
      child: Container(
        decoration: serializado
            ? const BoxDecoration(
                border: Border(
                  left: BorderSide(color: AppColors.secondary, width: 4),
                ),
              )
            : null,
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: serializado
                        ? AppColors.secondaryFixed
                        : AppColors.surfaceContainer,
                    borderRadius: AppRadius.brCampo,
                  ),
                  child: Icon(_icono, size: 20, color: AppColors.primary),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Row(
                        children: <Widget>[
                          Flexible(
                            child: serializado
                                ? Container(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 6,
                                      vertical: 2,
                                    ),
                                    decoration: const BoxDecoration(
                                      color: AppColors.secondary,
                                      borderRadius: AppRadius.brChico,
                                    ),
                                    child: Text(
                                      material.categoria.toUpperCase(),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: AppTypography.etiquetaChica.copyWith(
                                        color: AppColors.onSecondary,
                                        fontWeight: FontWeight.w700,
                                      ),
                                    ),
                                  )
                                : Text(
                                    material.categoria.toUpperCase(),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: AppTypography.etiquetaChica.copyWith(
                                      color: _colorDeClase,
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                          ),
                          // Lo que hay que poder rastrear uno por uno se
                          // anuncia acá: es lo que cambia cómo se cierra.
                          if (serializado) ...<Widget>[
                            const SizedBox(width: 6),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 6,
                                vertical: 2,
                              ),
                              decoration: const BoxDecoration(
                                color: AppColors.exitoFondo,
                                borderRadius: AppRadius.brChico,
                              ),
                              child: Text(
                                'Trazable',
                                style: AppTypography.etiquetaChica.copyWith(
                                  color: AppColors.exitoTexto,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                          ],
                        ],
                      ),
                      Text(
                        material.nombre,
                        style: AppTypography.cuerpoGrande.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      Text(material.detalle, style: AppTypography.cuerpoChico),
                    ],
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                  decoration: BoxDecoration(
                    color: serializado
                        ? AppColors.secondaryContainer
                        : AppColors.surfaceContainerHigh,
                    borderRadius: AppRadius.brChico,
                  ),
                  child: Text(
                    '${material.disponibles}${material.unidad == 'm' ? 'm' : ''} Disp.',
                    style: AppTypography.etiquetaChica.copyWith(
                      color: serializado
                          ? AppColors.onSecondaryContainer
                          : AppColors.primary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            if (material.clase == ClaseMaterial.consumible)
              material.razon == null ? _accionSimple() : _consumo(),
            if (material.clase == ClaseMaterial.bobina) _metraje(),
            if (serializado) _serie(context),
            if (material.clase == ClaseMaterial.terminal) _accionSimple(),
          ],
        ),
      ),
    );
  }

  IconData get _icono => switch (material.clase) {
        ClaseMaterial.consumible => Icons.electrical_services,
        ClaseMaterial.bobina => Icons.settings_ethernet,
        ClaseMaterial.serializado => Icons.router,
        ClaseMaterial.terminal => Icons.home_repair_service,
      };

  Widget _consumo() {
    final porcentaje = (material.consumo * 100).round();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                'Consumo: ${material.usados} de ${material.recibidos} '
                '${material.unidad} ($porcentaje%)',
                style: AppTypography.etiquetaChica,
              ),
            ),
            if (material.ordenesRelacionadas.isNotEmpty)
              Text(
                material.ordenesRelacionadas.join(', '),
                style: AppTypography.etiquetaChica.copyWith(
                  color: AppColors.secondary,
                ),
              ),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(AppRadius.circulo),
          child: LinearProgressIndicator(
            value: material.consumo,
            minHeight: 8,
            backgroundColor: AppColors.surfaceContainer,
            valueColor: const AlwaysStoppedAnimation<Color>(AppColors.secondary),
          ),
        ),
        if (material.razon != null) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          Container(
            padding: const EdgeInsets.all(AppSpacing.sm),
            decoration: const BoxDecoration(
              color: AppColors.surfaceContainerLow,
              borderRadius: AppRadius.brCampo,
            ),
            child: Row(
              children: <Widget>[
                Text('Razón OTs: ', style: AppTypography.etiquetaChica),
                Expanded(
                  child: Text(
                    material.razon!,
                    style: AppTypography.etiquetaChica.copyWith(
                      color: AppColors.onSurface,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                const _AccionChica(texto: 'Ver OTs', icono: Icons.chevron_right),
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _metraje() {
    return Column(
      children: <Widget>[
        Container(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
          decoration: const BoxDecoration(
            color: AppColors.surfaceContainerLow,
            borderRadius: AppRadius.brCampo,
          ),
          child: Row(
            children: <Widget>[
              Expanded(child: _ColumnaMetraje('Inicial', '${material.recibidos} m')),
              Expanded(
                child: _ColumnaMetraje(
                  'Tendido Hoy',
                  '${material.usados} m',
                  color: AppColors.secondary,
                ),
              ),
              Expanded(
                child: _ColumnaMetraje('Restante', '${material.disponibles} m'),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Row(
          children: <Widget>[
            const Icon(Icons.history, size: 13, color: AppColors.outline),
            const SizedBox(width: 4),
            Expanded(
              child: Text(
                material.ultimoMovimiento ?? '',
                style: AppTypography.etiquetaChica,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const _AccionChica(texto: 'Ajustar Metros', icono: Icons.straighten),
          ],
        ),
      ],
    );
  }

  /// El último movimiento del equipo trae dos datos: de dónde vino y a dónde
  /// fue. El diseño los pone en los dos extremos de la misma línea.
  List<String> get _partesDelMovimiento {
    final partes = (material.ultimoMovimiento ?? '').split(' · ');
    return partes.length >= 2 ? partes : <String>[partes.first];
  }

  Widget _serie(BuildContext contexto) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Container(
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: const BoxDecoration(
            color: AppColors.inverseSurface,
            borderRadius: AppRadius.brCampo,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      'SERIAL NUMBER (SN) · CÓDIGO BARRAS',
                      style: AppTypography.etiquetaChica.copyWith(
                        color: AppColors.surfaceDim,
                      ),
                    ),
                  ),
                  const Icon(Icons.verified, size: 13, color: AppColors.exitoFuerte),
                  const SizedBox(width: 4),
                  Text(
                    'Validado',
                    style: AppTypography.etiquetaChica.copyWith(
                      color: AppColors.exitoFuerte,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.sm),
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      'SN: ${material.serie}',
                      style: AppTypography.dato.copyWith(
                        color: AppColors.inverseOnSurface,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  Material(
                    color: AppColors.surfaceVariant.withValues(alpha: 0.2),
                    borderRadius: AppRadius.brCampo,
                    child: InkWell(
                      borderRadius: AppRadius.brCampo,
                      onTap: () async {
                        await Clipboard.setData(
                          ClipboardData(text: material.serie ?? ''),
                        );
                        if (!contexto.mounted) return;
                        ScaffoldMessenger.of(contexto).showSnackBar(
                          const SnackBar(content: Text('Serie copiada')),
                        );
                      },
                      child: const SizedBox(
                        width: 32,
                        height: 32,
                        child: Icon(
                          Icons.content_copy,
                          size: 16,
                          color: AppColors.surfaceBright,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              if (material.ultimoMovimiento != null) ...<Widget>[
                const SizedBox(height: AppSpacing.sm),
                const Divider(color: AppColors.outline, height: 1),
                const SizedBox(height: AppSpacing.sm),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    for (final (int i, String parte)
                        in _partesDelMovimiento.indexed) ...<Widget>[
                      if (i > 0) const SizedBox(width: AppSpacing.sm),
                      Expanded(
                        child: Text(
                          parte,
                          textAlign: i == 0 ? TextAlign.left : TextAlign.right,
                          style: AppTypography.etiquetaChica.copyWith(
                            color: AppColors.surfaceDim,
                            fontSize: 10,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        const Row(
          children: <Widget>[
            Expanded(
              child: _AccionChica(texto: 'Verificar MAC/SN', icono: Icons.barcode_reader),
            ),
            SizedBox(width: AppSpacing.sm),
            Expanded(
              child: _AccionChica(
                texto: 'Log Trazabilidad',
                icono: Icons.history_edu,
                color: AppColors.secondary,
              ),
            ),
          ],
        ),
      ],
    );
  }

  /// Lo que se recibe y se instala tal cual, sin barra de consumo: el diseño
  /// lo deja en una línea con su acción al lado.
  Widget _accionSimple() {
    return Row(
      children: <Widget>[
        Expanded(
          child: Text(
            material.ultimoMovimiento ?? '',
            style: AppTypography.etiquetaChica,
          ),
        ),
        _AccionChica(
          texto: material.clase == ClaseMaterial.terminal ? 'Asignar' : 'Ajustar',
          icono: material.clase == ClaseMaterial.terminal ? Icons.add : Icons.tune,
        ),
      ],
    );
  }
}

class _ColumnaMetraje extends StatelessWidget {
  const _ColumnaMetraje(this.titulo, this.valor, {this.color});

  final String titulo;
  final String valor;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Text(titulo, style: AppTypography.etiquetaChica),
        Text(
          valor,
          style: AppTypography.dato.copyWith(
            color: color ?? AppColors.onSurface,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }
}

/// Acción de una tarjeta de material. Todavía no hace nada: el módulo de
/// inventario no existe, y un botón que descuenta material sin backend sería
/// una mentira con consecuencias.
class _AccionChica extends StatelessWidget {
  const _AccionChica({
    required this.texto,
    required this.icono,
    this.color = AppColors.primary,
  });

  final String texto;
  final IconData icono;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minHeight: AppSpacing.objetivoTactil),
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
      alignment: Alignment.center,
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainer,
        borderRadius: AppRadius.brCampo,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Flexible(
            child: Text(
              texto,
              style: AppTypography.etiquetaChica.copyWith(
                color: color,
                fontWeight: FontWeight.w600,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 4),
          Icon(icono, size: 14, color: color),
        ],
      ),
    );
  }
}

/// Cómo agrupa el diseño el material en custodia.
enum _Categoria {
  todos('Todos', null),
  activos('Activos ONT', AppColors.secondary),
  consumibles('Consumibles', AppColors.exito);

  const _Categoria(this.etiqueta, this.punto);

  final String etiqueta;
  final Color? punto;

  bool incluye(MaterialEnCustodia material) => switch (this) {
        _Categoria.todos => true,
        _Categoria.activos => material.clase == ClaseMaterial.serializado,
        _Categoria.consumibles => material.clase != ClaseMaterial.serializado,
      };
}
