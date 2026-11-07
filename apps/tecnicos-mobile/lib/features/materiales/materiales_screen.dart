import '../../core/acciones/lector_de_codigo.dart';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/widgets/dexter_bloques.dart';

import '../../demo/field_mock_data.dart';
import '../../demo/kit_mock_data.dart';
import '../../core/storage/local_database.dart';
import 'devolucion_screen.dart';
import 'kit_de_jornada.dart';
import 'material_en_custodia.dart';
import 'pedir_a_bodega.dart';
import 'recepcion_del_kit.dart';
import 'widgets/tarjeta_de_recepcion.dart';
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
    this.pedidos,
    this.recepcion,
    this.leerCodigo,
    this.alRecibir,
  });

  final bool mostrarDatosFuturos;

  /// Lo que hay que confirmar al recibir el kit. Lo pasa el contenedor de la
  /// app; nulo en pruebas que no la miden, y entonces no se dibuja ni va a la red.
  final RecepcionDelKit? recepcion;

  /// El lector de códigos de la recepción. Solo las pruebas lo cambian.
  final LeerCodigo? leerCodigo;

  /// Después de confirmar o escanear: la custodia cambió en el servidor y hay
  /// que bajarla. En la app es la sincronización; sin él, se vuelve a leer.
  final Future<void> Function()? alRecibir;

  /// El kit ya leido. Se inyecta en las pruebas; en la aplicacion se lee solo.
  final KitDeJornada? kit;

  /// Los pedidos ya leidos. Igual que el kit: se inyectan en las pruebas.
  final List<PedidoEnCola>? pedidos;

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

  /// Lo que ya le pidió a bodega y todavía no llegó.
  List<PedidoEnCola> _pedidos = const <PedidoEnCola>[];

  /// Cuántas veces se bajó el kit desde que se abrió la pantalla.
  int _bajadasDelKit = 0;

  /// Confirmar o escanear cambia la custodia en el servidor. Bajarla escribe
  /// `local_kit`, y ese cambio vuelve a dibujar esta pantalla.
  Widget? _tarjetaDeRecepcion() {
    final RecepcionDelKit? recepcion = widget.recepcion;
    if (recepcion == null) return null;
    return TarjetaDeRecepcion(
      recepcion: recepcion,
      leerCodigo: widget.leerCodigo ?? leerConLaCamara,
      alCambiar: widget.alRecibir ?? _cargar,
      recargarCon: _bajadasDelKit,
    );
  }

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
      // Un kit bajado del servidor puede traer una entrega nueva: la recepción
      // se vuelve a leer (la pestaña queda viva y no se entera sola).
      if (evento.tabla == 'local_kit') _bajadasDelKit++;
      if (evento.tabla == 'local_kit' ||
          evento.tabla == 'cola_movimientos_material' ||
          evento.tabla == 'cola_pedidos_material') {
        _cargar();
      }
    });
  }

  Future<void> _cargar() async {
    // UN KIT INYECTADO SIGNIFICA «esta pantalla no lee la base».
    //
    // Y no es una comodidad de las pruebas: con el kit puesto desde afuera, ir
    // a buscar los pedidos a SQLite deja la pantalla esperando un futuro que,
    // bajo el reloj falso de una prueba de widget, nunca resuelve — la pantalla
    // se queda en «cargando» y no dibuja nada. Pasó: rompió 18 casos de golpe,
    // y ninguno decía «no hay base», decían «no encuentro ese texto».
    if (widget.kit != null) {
      setState(() {
        _kit = widget.kit;
        _pedidos = widget.pedidos ?? const <PedidoEnCola>[];
        _cargando = false;
      });
      return;
    }
    final List<PedidoEnCola> pedidos =
        widget.pedidos ?? await leerPedidosDeMaterial();
    final kit = await KitDeJornada.leer();
    if (!mounted) return;
    setState(() {
      _kit = kit;
      _pedidos = pedidos;
      _cargando = false;
    });
  }

  Future<void> _pedirABodega(List<MaterialEnCustodia> materiales) async {
    final bool quedo = await abrirHojaDePedido(
      context,
      materiales: materiales,
    );
    if (!mounted || !quedo) return;
    _decir('Pedido guardado. Sube cuando haya señal.');
    await _cargar();
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

    final Widget? tarjeta = _tarjetaDeRecepcion();

    if (todos.isEmpty) {
      const Widget vacio = Center(
        child: DexterEmptyState(
          icono: Icons.inventory_2_outlined,
          titulo: 'Mi kit y custodia',
          mensaje: 'Todavía no hay material entregado a tu nombre. Aparece '
              'cuando la bodega registre la entrega y haya señal para '
              'sincronizar.',
        ),
      );
      // Sin nada en custodia puede haber equipos apartados por escanear: la
      // recepción va arriba también acá.
      return ColoredBox(
        color: AppColors.surface,
        child: tarjeta == null
            ? vacio
            : Column(children: <Widget>[
                Padding(
                  padding: const EdgeInsets.fromLTRB(
                      AppSpacing.margen, AppSpacing.md, AppSpacing.margen, 0),
                  child: tarjeta,
                ),
                const Expanded(child: vacio),
              ]),
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
          ?tarjeta,
          _recepcionDelKit(todos),
          if (_kit != null && _kit!.conNovedad.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            _novedades(_kit!.conNovedad),
          ],
          const SizedBox(height: AppSpacing.md),
          _barraDeAcciones(todos),
          if (_pedidos.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            _pedidosEnCurso(_pedidos),
          ],
          const SizedBox(height: AppSpacing.md),
          _filtros(todos),
          const SizedBox(height: AppSpacing.md),
          Row(
            children: <Widget>[
              // `Expanded` y no un `Spacer` suelto: a 360 px —el Galaxy A que
              // una empresa le compra a una cuadrilla— los dos textos juntos
              // desbordaban 153 px, medido por la guarda de ancho real. El
              // título es el que cede, porque el que importa de los dos es el
              // conteo.
              Expanded(
                child: Text(
                  'Materiales en Custodia',
                  style: AppTypography.tituloChico,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: AppSpacing.xs),
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
            _TarjetaMaterial(
              material: material,
              alVerificar: _verificarSerial,
            ),
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
  /// Las novedades, una por una y con su camino.
  ///
  /// POR QUÉ NO ALCANZA UN CONTADOR
  /// ------------------------------
  /// Antes esto era "Novedades: 1". Dos situaciones que se resuelven de forma
  /// completamente distinta se veían idénticas:
  ///
  /// - Un **descuadre** lo arregla el técnico: explica qué pasó con el
  ///   material y la jornada cierra.
  /// - Un **conflicto de identidad** no: el equipo figura instalado en otra
  ///   orden, y eso lo resuelve alguien con acceso al inventario. Insistir
  ///   desde la vereda no lo destraba, y peor, el técnico puede creer que el
  ///   serial que tiene en la mano es el equivocado.
  ///
  /// El dominio ya los distinguía —`resultado` es `descuadre`, `conflicto` o
  /// `rechazado`, cada uno con su título—. Lo que faltaba era dibujarlo.
  Widget _novedades(List<MovimientoConNovedad> novedades) {
    if (novedades.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          novedades.length == 1 ? 'Una novedad' : '${novedades.length} novedades',
          style: AppTypography.tituloChico,
        ),
        const SizedBox(height: AppSpacing.sm),
        for (final MovimientoConNovedad n in novedades)
          Container(
            margin: const EdgeInsets.only(bottom: AppSpacing.sm),
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color: AppColors.surfaceContainerLowest,
              borderRadius: AppRadius.brTarjeta,
              border: Border.all(
                color: n.esDeIdentidad ? AppColors.error : AppColors.outlineVariant,
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Icon(
                      n.esDeIdentidad
                          ? Icons.fingerprint
                          : Icons.difference_outlined,
                      size: 16,
                      color: n.esDeIdentidad
                          ? AppColors.error
                          : AppColors.onSurfaceVariant,
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        n.titulo,
                        style: AppTypography.etiquetaGrande.copyWith(
                          color: n.esDeIdentidad
                              ? AppColors.error
                              : AppColors.onSurface,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.xs),
                Text(n.material, style: AppTypography.cuerpo),
                // El serial en monoespaciada: se compara carácter por carácter
                // contra la etiqueta pegada al equipo.
                if (n.serie.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 2),
                  Text(
                    'Serie ${n.serie}',
                    style: AppTypography.datoChico
                        .copyWith(color: AppColors.onSurfaceVariant),
                  ),
                ],
                if (!n.esDeIdentidad && n.cantidad.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 2),
                  Text(
                    'Cantidad registrada: ${n.cantidad}',
                    style: AppTypography.etiquetaChica,
                  ),
                ],
                if (n.ordenNumero != null) ...<Widget>[
                  const SizedBox(height: 2),
                  Text('OT #${n.ordenNumero}',
                      style: AppTypography.etiquetaChica),
                ],
                if (n.motivo.isNotEmpty) ...<Widget>[
                  const SizedBox(height: AppSpacing.xs),
                  Text(n.motivo, style: AppTypography.cuerpoChico),
                ],
                const SizedBox(height: AppSpacing.sm),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(AppSpacing.sm),
                  decoration: BoxDecoration(
                    color: n.esDeIdentidad
                        ? AppColors.errorContainer
                        : AppColors.surfaceContainerLow,
                    borderRadius: AppRadius.brCampo,
                  ),
                  child: Text(
                    n.queHacer,
                    style: AppTypography.cuerpoChico.copyWith(
                      color: n.esDeIdentidad
                          ? AppColors.onErrorContainer
                          : AppColors.onSurface,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }

  /// «12» o «12,5»: sin ceros de relleno, con coma.
  static String numero(double v) => v == v.roundToDouble()
      ? v.round().toString()
      : v.toStringAsFixed(1).replaceAll('.', ',');

  /// Suma por unidad: «320 m» o «38 unidades · 2 rollos».
  static String porUnidad(Iterable<MaterialEnCustodia> ms,
      double Function(MaterialEnCustodia) cuanto) {
    final Map<String, double> suma = <String, double>{};
    for (final MaterialEnCustodia m in ms) {
      suma[m.unidad] = (suma[m.unidad] ?? 0) + cuanto(m);
    }
    return suma.entries
        .map((MapEntry<String, double> e) => '${numero(e.value)} ${e.key}')
        .join(' · ');
  }

  Widget _resumenPorClase(List<MaterialEnCustodia> materiales) {
    Iterable<MaterialEnCustodia> de(ClaseDeResumen c) =>
        materiales.where((MaterialEnCustodia m) => m.claseDeResumen == c);
    final List<Widget> celdas = <Widget>[];
    final Iterable<MaterialEnCustodia> equipos = de(ClaseDeResumen.equipos);
    if (equipos.isNotEmpty) {
      final int instalados = equipos.fold<int>(
          0, (int n, MaterialEnCustodia m) => n + m.instaladas.length);
      celdas.add(_CeldaDeResumen(
        rotulo: 'EQUIPOS',
        valor: numero(equipos.fold<double>(
            0, (double n, MaterialEnCustodia m) => n + m.enMano)),
        detalle: instalados == 1 ? '1 instalado' : '$instalados instalados',
      ));
    }
    final Iterable<MaterialEnCustodia> cable = de(ClaseDeResumen.cable);
    if (cable.isNotEmpty) {
      celdas.add(_CeldaDeResumen(
        rotulo: 'CABLE',
        valor: porUnidad(cable, (MaterialEnCustodia m) => m.enMano),
        detalle: '${porUnidad(cable, (MaterialEnCustodia m) => m.usado)} usados',
      ));
    }
    final Iterable<MaterialEnCustodia> otros = de(ClaseDeResumen.consumibles);
    if (otros.isNotEmpty) {
      celdas.add(_CeldaDeResumen(
        rotulo: 'CONSUMIBLES',
        valor: porUnidad(otros, (MaterialEnCustodia m) => m.enMano),
        detalle: '${porUnidad(otros, (MaterialEnCustodia m) => m.usado)} usados',
      ));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text('EN TU MANO',
            style: AppTypography.labelCaption.copyWith(color: AppColors.outline)),
        const SizedBox(height: AppSpacing.xs),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            for (int i = 0; i < celdas.length; i++) ...<Widget>[
              if (i > 0) const SizedBox(width: AppSpacing.sm),
              Expanded(child: celdas[i]),
            ],
          ],
        ),
      ],
    );
  }

  Widget _recepcionDelKit(List<MaterialEnCustodia> materiales) {
    final int pendientes = _kit?.sinSubir ?? 0;
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
              // El diseño pone el ícono a la IZQUIERDA, en su caja, y encima
              // del título un rótulo que dice de qué habla la tarjeta.
              Container(
                width: 44,
                height: 44,
                alignment: Alignment.center,
                decoration: const BoxDecoration(
                  color: AppColors.surfaceContainer,
                  borderRadius: AppRadius.brTarjeta,
                ),
                child: const Icon(Icons.inventory_2,
                    size: 24, color: AppColors.secondary),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      'ESTADO DE CUSTODIA',
                      style: AppTypography.labelBadge
                          .copyWith(color: AppColors.outline),
                    ),
                    Text('Mi Kit Diario', style: AppTypography.headlineMd),
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
                    // Lo registrado que todavía no salió del teléfono.
                    //
                    // El dato estaba en el kit y no se dibujaba en ninguna
                    // parte: alguien podía registrar consumo sin señal toda la
                    // mañana y esta pantalla se veía idéntica a tenerlo todo
                    // enviado. Lo encontró la prueba que compara estados: las
                    // dos capturas salían iguales byte a byte.
                    if (pendientes > 0) ...<Widget>[
                      const SizedBox(height: 4),
                      Row(
                        children: <Widget>[
                          const Icon(Icons.cloud_upload_outlined,
                              size: 13, color: AppColors.onSurfaceVariant),
                          const SizedBox(width: 4),
                          Flexible(
                            child: Text(
                              pendientes == 1
                                  ? '1 movimiento esperando señal'
                                  : '$pendientes movimientos esperando señal',
                              style: AppTypography.etiquetaChica,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
          // POR CLASE, CON SU UNIDAD (18/10/2026). Las cifras de antes
          // contaban TIPOS de material («Materiales 5 · Usados 3»), no cuánto
          // tiene el técnico; y sumar cantidades mezclaría ONTs con metros de
          // cable. Acá cada clase dice lo que hay en la mano, en lo suyo.
          const SizedBox(height: AppSpacing.md),
          _resumenPorClase(materiales),
        ],
      ),
    );
  }


  /// Cuantos renglones quedan por devolver.
  ///
  /// Cuenta renglones y no cantidades por la misma razon que la cabecera:
  /// sumar unidades con metros da un total que no significa nada. Cuanto hay
  /// de cada uno se ve en su tarjeta, con su unidad.
  String _fraseDeCierre() {
    final List<MaterialEnCustodia> materiales =
        _kit?.materiales ?? const <MaterialEnCustodia>[];
    final int pendientes =
        materiales.where((MaterialEnCustodia m) => m.disponibles > 0).length;

    if (pendientes == 0) {
      return 'No te queda material por devolver a la bodega.';
    }
    return pendientes == 1
        ? 'Te queda 1 material por conciliar y devolver a bodega.'
        : 'Te quedan $pendientes materiales por conciliar y devolver a bodega.';
  }

  /// Escanea un serial y dice CUAL de tus materiales es.
  ///
  /// La pregunta real: el tecnico tiene cinco cajas iguales en el baul y quiere
  /// saber si la que agarro es suya y cual es. Responderla a ojo es comparar
  /// catorce caracteres cinco veces.
  ///
  /// Lo que NO hace es buscar en el catalogo de la empresa: si el serial no esta
  /// en TU custodia, lo correcto es decir eso --«este equipo no es tuyo»-- y no
  /// ir a preguntarle al servidor, que ademas no contestaria sin senal.
  Future<void> _buscarPorSerial(List<MaterialEnCustodia> materiales) async {
    final String? leido = await LectorDeCodigo.abrir(
      context,
      titulo: 'Buscar en tu kit',
      ayuda: 'Apuntá al código del equipo para ver si está a tu nombre.',
    );
    if (leido == null || !mounted) return;

    MaterialEnCustodia? encontrado;
    String serieEncontrada = '';
    for (final MaterialEnCustodia m in materiales) {
      for (final String s in m.todasLasSeries) {
        if (mismoSerial(s, leido)) {
          encontrado = m;
          serieEncontrada = s;
          break;
        }
      }
      if (encontrado != null) break;
    }

    if (!mounted) return;
    if (encontrado == null) {
      _decir(
        'Ese equipo no está en tu custodia.\nLeído: $leido',
        esProblema: true,
      );
      return;
    }
    // Dice dónde está: en la camioneta o ya instalado en una orden.
    final SerieInstalada? inst = encontrado.instaladas[serieEncontrada];
    _decir(
      '${encontrado.nombre} · $serieEncontrada\n'
      '${inst == null ? 'En tu poder' : textoDeInstalada(inst)}',
    );
  }

  /// Compara lo escaneado contra el serial de ESTA tarjeta.
  Future<void> _verificarSerial(MaterialEnCustodia material) async {
    final String? leido = await LectorDeCodigo.abrir(
      context,
      titulo: 'Verificar ${material.nombre}',
      ayuda: 'Apuntá al código del equipo que tenés en la mano.',
    );
    if (leido == null || !mounted) return;

    final List<String> series = material.todasLasSeries;
    final String coincide = series.firstWhere(
      (String s) => mismoSerial(s, leido),
      orElse: () => '',
    );
    _decir(
      coincide.isNotEmpty
          ? 'Coincide: $coincide'
          : 'NO coincide con ninguna serie de ${material.nombre}.\nLeíste $leido',
      esProblema: coincide.isEmpty,
    );
  }

  /// Un aviso en pantalla. Se dice SIEMPRE, tambien cuando sale bien: un
  /// escaneo que no responde nada deja al tecnico sin saber si leyo o no.
  void _decir(String texto, {bool esProblema = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(texto),
        duration: const Duration(seconds: 5),
        backgroundColor: esProblema ? AppColors.error : null,
      ),
    );
  }

  Widget _barraDeAcciones(List<MaterialEnCustodia> materiales) {
    // Ícono y una palabra, como en Ejecutar (18/10/2026).
    return Row(
      children: <Widget>[
        Expanded(
          child: DexterAccionCompacta(
            icono: Icons.qr_code_scanner,
            texto: 'Escanear',
            descripcion: 'Escanear un equipo para ver si está a tu nombre',
            alTocar: () => _buscarPorSerial(materiales),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: DexterAccionCompacta(
            icono: Icons.local_shipping,
            texto: 'Pedir',
            descripcion: 'Pedir material a bodega',
            alTocar: () => _pedirABodega(materiales),
          ),
        ),
      ],
    );
  }

  /// Lo que ya le pidió a bodega.
  ///
  /// SE MUESTRA PORQUE SIN ESTO NO SE SABE SI SE PIDIO. Un pedido que se encola
  /// sin señal no produce ninguna señal visible, y el técnico vuelve a pedir lo
  /// mismo —o peor: deja de pedir creyendo que ya pidió—. La idempotencia evita
  /// el duplicado del lado del servidor; esta tira evita la duda del lado de la
  /// persona, que es otro problema.
  Widget _pedidosEnCurso(List<PedidoEnCola> pedidos) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: AppColors.fondoHundido,
        borderRadius: BorderRadius.circular(AppRadius.tarjeta),
        border: Border.all(color: AppColors.borde),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.local_shipping_outlined,
                size: 16,
                color: AppColors.textoSecundario,
              ),
              const SizedBox(width: AppSpacing.xs),
              Text('Pedidos a bodega', style: AppTypography.etiquetaChica),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          for (final PedidoEnCola p in pedidos)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      '${p.cantidad} · ${p.material}',
                      style: AppTypography.cuerpoChico,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Text(
                    p.comoVa,
                    style: AppTypography.etiquetaChica.copyWith(
                      color: p.esProblema
                          ? AppColors.error
                          : AppColors.textoSecundario,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
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
          // Este botón era un Container sin acción: se veía como un botón,
          // se tocaba y no pasaba nada. Y era el ÚNICO camino hacia el cierre
          // de jornada, que estaba construido y probado desde hacía días sin
          // que nadie pudiera llegar. Un botón que no hace nada es peor que
          // no tenerlo: la persona cree que ya dio el paso.
          InkWell(
            borderRadius: AppRadius.brTarjeta,
            onTap: () async {
              await Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const DevolucionScreen(),
                ),
              );
              if (mounted) await _cargar();
            },
            child: Container(
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
                // El texto se achica antes que cortarse: es el botón que cierra
                // la jornada y «Preparar Devolución al Depós…» no se entiende.
                // A 360 px desbordaba 190 px, medido por la guarda de ancho
                // real — el botón salía de la pantalla sin que nada avisara.
                Flexible(
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(
                      'Preparar Devolución al Depósito',
                      style: AppTypography.etiquetaGrande.copyWith(
                        color: AppColors.primary,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                const Icon(Icons.arrow_forward, size: 18, color: AppColors.primary),
              ],
            ),
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
/// «Instalado en OT #1849», o «Instalado · sin subir» si no llegó todavía.
String textoDeInstalada(SerieInstalada inst) {
  final String donde =
      inst.ordenNumero == null ? 'Instalado' : 'Instalado en OT #${inst.ordenNumero}';
  return inst.sinSubir ? '$donde · sin subir' : donde;
}

/// Una celda del resumen de arriba: la clase, lo que hay en la mano y un
/// detalle chico.
class _CeldaDeResumen extends StatelessWidget {
  const _CeldaDeResumen({
    required this.rotulo,
    required this.valor,
    required this.detalle,
  });

  final String rotulo;
  final String valor;
  final String detalle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainer,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(rotulo,
              style: AppTypography.labelCaption.copyWith(color: AppColors.outline)),
          const SizedBox(height: 2),
          Text(valor,
              style: AppTypography.tituloChico.copyWith(color: AppColors.onSurface)),
          Text(detalle, style: AppTypography.etiquetaChica),
        ],
      ),
    );
  }
}

/// Un material del kit.
///
/// LO PRIMERO ES LO QUE TIENE EN LA MANO (18/10/2026): en grande y con su
/// unidad. Lo recibido y lo usado van en chico, debajo. Un equipo con serie
/// muestra TODAS sus series —antes, solo la primera— y dónde está cada una:
/// en la camioneta o instalada en una orden.
class _TarjetaMaterial extends StatelessWidget {
  const _TarjetaMaterial({required this.material, this.alVerificar});

  final void Function(MaterialEnCustodia)? alVerificar;

  final MaterialEnCustodia material;

  IconData get _icono => switch (material.clase) {
        ClaseMaterial.consumible => Icons.electrical_services,
        ClaseMaterial.bobina => Icons.settings_ethernet,
        ClaseMaterial.serializado => Icons.router,
        ClaseMaterial.terminal => Icons.home_repair_service,
      };

  @override
  Widget build(BuildContext context) {
    final bool conSeries = material.clase == ClaseMaterial.serializado &&
        material.todasLasSeries.isNotEmpty;
    final String unidad = material.unidad;

    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
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
              Container(
                width: 40,
                height: 40,
                decoration: const BoxDecoration(
                  color: AppColors.surfaceContainer,
                  borderRadius: AppRadius.brCampo,
                ),
                child: Icon(_icono, size: 20, color: AppColors.primary),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    if (material.categoria.isNotEmpty)
                      Text(
                        material.categoria.toUpperCase(),
                        style: AppTypography.etiquetaChica.copyWith(
                          color: AppColors.outline,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    Text(
                      material.nombre,
                      style: AppTypography.cuerpoGrande
                          .copyWith(fontWeight: FontWeight.w600),
                    ),
                    if (material.detalle.isNotEmpty)
                      Text(material.detalle, style: AppTypography.cuerpoChico),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              // EN LA MANO, EN GRANDE: el número y su unidad juntos, para que
              // nunca se lea un número suelto.
              Text.rich(
                TextSpan(
                  children: <InlineSpan>[
                    TextSpan(
                      text: _MaterialesScreenState.numero(material.enMano),
                      style: AppTypography.headlineMd.copyWith(
                        color: material.enMano < 0
                            ? AppColors.error
                            : AppColors.onSurface,
                      ),
                    ),
                    TextSpan(
                      text: ' $unidad',
                      style: AppTypography.etiquetaChica,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Recibido ${_MaterialesScreenState.numero(material.recibido)} · '
            'usado ${_MaterialesScreenState.numero(material.usado)}',
            style: AppTypography.etiquetaChica,
          ),
          if (conSeries) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            for (final String serie in material.todasLasSeries)
              _filaDeSerie(context, serie),
            if (alVerificar != null) ...<Widget>[
              const SizedBox(height: AppSpacing.xs),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () => alVerificar!(material),
                  icon: const Icon(Icons.barcode_reader, size: 18),
                  label: const Text('Verificar un equipo'),
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }

  Widget _filaDeSerie(BuildContext context, String serie) {
    final SerieInstalada? inst = material.instaladas[serie];
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              serie,
              style: AppTypography.dato.copyWith(color: AppColors.onSurface),
            ),
          ),
          if (inst == null)
            DexterPastilla.enRegla(texto: 'En tu poder')
          else
            DexterPastilla.neutra(texto: textoDeInstalada(inst)),
          IconButton(
            tooltip: 'Copiar $serie',
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.copy, size: 16),
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: serie));
              if (!context.mounted) return;
              ScaffoldMessenger.maybeOf(context)?.showSnackBar(
                const SnackBar(content: Text('Serie copiada')),
              );
            },
          ),
        ],
      ),
    );
  }
}



/// Cómo agrupa el diseño el material en custodia.
enum _Categoria {
  todos('Todos', null),
  equipos('Equipos', AppColors.secondary),
  cable('Cable', AppColors.primary),
  consumibles('Consumibles', AppColors.exito);

  const _Categoria(this.etiqueta, this.punto);

  final String etiqueta;
  final Color? punto;

  bool incluye(MaterialEnCustodia material) => switch (this) {
        _Categoria.todos => true,
        _Categoria.equipos => material.claseDeResumen == ClaseDeResumen.equipos,
        _Categoria.cable => material.claseDeResumen == ClaseDeResumen.cable,
        _Categoria.consumibles =>
          material.claseDeResumen == ClaseDeResumen.consumibles,
      };
}
