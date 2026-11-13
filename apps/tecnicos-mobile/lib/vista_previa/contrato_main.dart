/// PROTOTIPO · CREAR EL CONTRATO DESDE LA APP (13/11/2026). NO ES PRODUCTO.
///
/// Para mostrar cómo quedaría el recorrido de una instalación nueva, de punta a
/// punta, antes de construirlo: la orden que despacha el Supervisor, iniciar,
/// llegar, el proceso técnico y --lo que el usuario quiere agilizar-- crear el
/// contrato del cliente, que hoy el técnico hace a mano dentro de WispHub.
///
///     flutter run -t lib/vista_previa/contrato_main.dart
///
/// Todo es de ejemplo y NADA sale del teléfono: no hay servidor, ni sesión, ni
/// WispHub, ni SmartOLT. Usa el tema real de la app para que se vea como ella.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';

void main() => runApp(const _Prototipo());

class _Prototipo extends StatelessWidget {
  const _Prototipo();

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Contrato · prototipo',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.lightTheme,
        home: const _Recorrido(),
      );
}

/// Los momentos del recorrido, en el orden en que los vive el técnico.
enum _Etapa { asignada, enRuta, enSitio, contrato, creando, listo }

/// La solicitud que el cliente llenó desde el link. De ejemplo.
class _Solicitud {
  static const String nombre = 'Laura Gómez Ríos';
  static const String cedula = 'CC 1.043.000.000';
  static const String telefono = '300 000 0000';
  static const String direccion = 'Cra 21 # 45-12, Villa Estadio, Soledad';
  static const String gps = '10.9108, -74.8186 (±6 m)';
  static const String plan = 'Fibra 300 Mb · \$85.000/mes';
  static const String enviada = 'Enviada el 10/11 · aprobada el 11/11';
}

class _Recorrido extends StatefulWidget {
  const _Recorrido();

  @override
  State<_Recorrido> createState() => _EstadoRecorrido();
}

class _EstadoRecorrido extends State<_Recorrido> {
  _Etapa _etapa = _Etapa.asignada;
  bool _sinSenal = false;

  // Lo que el técnico va haciendo en sitio.
  String? _serialOnu;
  String? _potencia;
  bool _fibraTendida = false;
  bool _fotos = false;
  bool _wifi = false;

  // Lo que la plataforma propone para el servicio. El técnico lo puede cambiar.
  String _zona = 'Soledad · Router Norte';
  String _ip = '10.20.5.47';
  final String _usuario = 'laura-gomez-301';

  final List<List<Offset?>> _trazos = <List<Offset?>>[];

  /// Mientras el dedo está en el recuadro de la firma, la pantalla no se
  /// desplaza: si no, el trazo lo gana el scroll y la firma nunca se dibuja.
  bool _firmando = false;
  bool get _hayFirma => _trazos.any((List<Offset?> t) => t.length > 2);

  bool get _procesoListo =>
      _serialOnu != null && _potencia != null && _fibraTendida && _fotos && _wifi;

  void _ir(_Etapa e) => setState(() => _etapa = e);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.fondo,
      appBar: AppBar(
        title: Text(_titulo()),
        leading: _etapa == _Etapa.asignada || _etapa == _Etapa.creando
            ? null
            : IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: () => _ir(_Etapa.values[_etapa.index - 1]),
              ),
        actions: <Widget>[
          Row(
            children: <Widget>[
              Text('Sin señal',
                  style: AppTypography.etiquetaChica
                      .copyWith(color: AppColors.textoSobreOscuro)),
              Switch(
                value: _sinSenal,
                onChanged: (bool v) => setState(() => _sinSenal = v),
              ),
            ],
          ),
        ],
      ),
      body: Column(
        children: <Widget>[
          const _FranjaPrototipo(),
          _Pasos(actual: _etapa),
          Expanded(child: _cuerpo()),
        ],
      ),
    );
  }

  String _titulo() => switch (_etapa) {
        _Etapa.asignada => 'OT #301 · Instalación',
        _Etapa.enRuta => 'En camino',
        _Etapa.enSitio => 'Instalando',
        _Etapa.contrato => 'Crear el contrato',
        _Etapa.creando => 'Creando el contrato',
        _Etapa.listo => 'Contrato creado',
      };

  Widget _cuerpo() => switch (_etapa) {
        _Etapa.asignada => _asignada(),
        _Etapa.enRuta => _enRuta(),
        _Etapa.enSitio => _enSitio(),
        _Etapa.contrato => _contrato(),
        _Etapa.creando => _Creando(alTerminar: () => _ir(_Etapa.listo)),
        _Etapa.listo => _listo(),
      };

  // ------------------------------------------------------------------------
  //  1 · LA ORDEN QUE DESPACHÓ EL SUPERVISOR
  // ------------------------------------------------------------------------
  Widget _asignada() => _Lista(children: <Widget>[
        _Tarjeta(
          oscura: true,
          children: <Widget>[
            Row(children: <Widget>[
              const Icon(Icons.circle, size: 10, color: Color(0xFF34D399)),
              const SizedBox(width: 6),
              Text('ASIGNADA · OT #301',
                  style: AppTypography.etiqueta
                      .copyWith(color: AppColors.textoSobreOscuro)),
            ]),
            const SizedBox(height: 6),
            Text('Despachada por el Supervisor IA · hoy 8:10',
                style: AppTypography.cuerpoChico
                    .copyWith(color: AppColors.textoSobreOscuro.withValues(alpha: .7))),
          ],
        ),
        _Tarjeta(children: <Widget>[
          Text('INSTALACIÓN NUEVA',
              style: AppTypography.etiqueta.copyWith(color: AppColors.azulAccion)),
          const SizedBox(height: 4),
          Text(_Solicitud.nombre, style: AppTypography.tituloMedio),
          const SizedBox(height: 4),
          Text(_Solicitud.direccion, style: AppTypography.cuerpo),
          const SizedBox(height: 4),
          Text(_Solicitud.plan, style: AppTypography.cuerpoChico),
          const Divider(height: 24),
          const _Dato(icono: Icons.description_outlined,
              texto: 'Solicitud completa: datos, cédula, recibo y autorizaciones'),
          const _Dato(icono: Icons.verified_outlined,
              texto: 'Factibilidad aprobada · zona de la Cuadrilla #5'),
          const _Dato(icono: Icons.inventory_2_outlined,
              texto: 'Material apartado: ONU, 1 roseta, 100 m de drop'),
        ]),
        _Boton('Iniciar ruta', Icons.navigation_outlined, () => _ir(_Etapa.enRuta)),
      ]);

  // ------------------------------------------------------------------------
  //  2 · EN CAMINO
  // ------------------------------------------------------------------------
  Widget _enRuta() => _Lista(children: <Widget>[
        _Tarjeta(children: <Widget>[
          Text('Vas hacia', style: AppTypography.etiquetaChica),
          Text(_Solicitud.direccion, style: AppTypography.tituloChico),
          const SizedBox(height: 12),
          Container(
            height: 160,
            decoration: BoxDecoration(
              color: AppColors.infoFondo,
              borderRadius: AppRadius.brTarjeta,
            ),
            alignment: Alignment.center,
            child: const Icon(Icons.map_outlined, size: 48, color: AppColors.info),
          ),
          const SizedBox(height: 8),
          Text('El cliente recibió por WhatsApp: «el técnico va en camino».',
              style: AppTypography.cuerpoChico),
        ]),
        _Boton('Llegué', Icons.place_outlined, () => _ir(_Etapa.enSitio)),
        Text('Al tocar «Llegué» queda la hora y el punto GPS en la orden.',
            textAlign: TextAlign.center, style: AppTypography.cuerpoChico),
      ]);

  // ------------------------------------------------------------------------
  //  3 · EL PROCESO TÉCNICO (la plantilla de instalación)
  // ------------------------------------------------------------------------
  Widget _enSitio() => _Lista(children: <Widget>[
        Text('Lo que pide la plantilla de instalación',
            style: AppTypography.etiqueta),
        _Paso(
          hecho: _fibraTendida,
          titulo: 'Tender la fibra',
          detalle: _fibraTendida ? '85 m de drop' : 'Cuántos metros usaste',
          accion: 'Anotar 85 m',
          alTocar: () => setState(() => _fibraTendida = true),
        ),
        _Paso(
          hecho: _serialOnu != null,
          titulo: 'Instalar la ONU',
          detalle: _serialOnu ?? 'Escanea el código de barras de la ONU',
          accion: 'Escanear',
          icono: Icons.qr_code_scanner,
          alTocar: () => setState(() => _serialOnu = 'ZTEGC8F21A44'),
        ),
        _Paso(
          hecho: _potencia != null,
          titulo: 'Medir la potencia',
          detalle: _potencia ?? 'La pide la plataforma a la OLT',
          accion: 'Medir',
          icono: Icons.speed,
          alTocar: () => setState(() => _potencia = '−19,8 dBm · en rango'),
        ),
        _Paso(
          hecho: _fotos,
          titulo: 'Fotos de evidencia',
          detalle: _fotos ? '4 fotos, con la marca de la empresa' : 'Roseta, ONU, potencia y fachada',
          accion: 'Tomar',
          icono: Icons.photo_camera_outlined,
          alTocar: () => setState(() => _fotos = true),
        ),
        _Paso(
          hecho: _wifi,
          titulo: 'WiFi probada con el cliente',
          detalle: _wifi ? 'Prueba de velocidad: 298 Mb' : 'Conecta un equipo del cliente',
          accion: 'Listo',
          alTocar: () => setState(() => _wifi = true),
        ),
        _Boton(
          'Seguir al contrato',
          Icons.assignment_outlined,
          _procesoListo ? () => _ir(_Etapa.contrato) : null,
        ),
        if (!_procesoListo)
          Text('Toca cada paso para completarlo (prototipo).',
              textAlign: TextAlign.center, style: AppTypography.cuerpoChico),
      ]);

  // ------------------------------------------------------------------------
  //  4 · EL CONTRATO: lo que se quiere agilizar
  // ------------------------------------------------------------------------
  Widget _contrato() => _Lista(
      fija: _firmando,
      children: <Widget>[
        _Bloque(
          titulo: 'El cliente',
          origen: 'Ya lo llenó el cliente en la solicitud',
          colorOrigen: AppColors.exitoTexto,
          fondoOrigen: AppColors.exitoFondo,
          filas: const <List<String>>[
            <String>['Nombre', _Solicitud.nombre],
            <String>['Documento', _Solicitud.cedula],
            <String>['Teléfono', _Solicitud.telefono],
            <String>['Dirección', _Solicitud.direccion],
            <String>['Ubicación', _Solicitud.gps],
            <String>['Plan', _Solicitud.plan],
            <String>['Autorizaciones', 'Habeas data ✓ · Centrales de riesgo ✓'],
          ],
          pie: _Solicitud.enviada,
          accion: 'Corregir un dato',
        ),
        _Bloque(
          titulo: 'El servicio',
          origen: 'Lo propone la plataforma; puedes cambiarlo',
          colorOrigen: AppColors.azulAccion,
          fondoOrigen: AppColors.infoFondo,
          filas: <List<String>>[
            <String>['Zona / router', _zona],
            <String>['IP', '$_ip  (la siguiente libre)'],
            <String>['Usuario PPPoE', _usuario],
          ],
          pie: 'La zona sale de la cuadrilla y del barrio; la IP, del rango de esa zona.',
          accion: 'Cambiar',
          alAccion: _cambiarServicio,
        ),
        _Bloque(
          titulo: 'La instalación',
          origen: 'Lo hiciste en los pasos anteriores',
          colorOrigen: AppColors.textoSecundario,
          fondoOrigen: AppColors.inactivoFondo,
          filas: <List<String>>[
            <String>['Serial de la ONU', _serialOnu ?? '—'],
            <String>['Potencia', _potencia ?? '—'],
            <String>['Fibra', '85 m'],
            <String>['Evidencias', '4 fotos con marca'],
          ],
        ),
        _Tarjeta(children: <Widget>[
          Row(children: <Widget>[
            Text('Firma del cliente', style: AppTypography.tituloChico),
            const Spacer(),
            if (_hayFirma)
              TextButton(
                style: TextButton.styleFrom(minimumSize: const Size(0, 40)),
                onPressed: () => setState(_trazos.clear),
                child: const Text('Borrar'),
              ),
          ]),
          const SizedBox(height: 4),
          Text('Acepta el contrato y la instalación recibida.',
              style: AppTypography.cuerpoChico),
          const SizedBox(height: 8),
          _PadDeFirma(
            trazos: _trazos,
            alCambiar: () => setState(() {}),
            alEmpezar: () => setState(() => _firmando = true),
            alTerminar: () => setState(() => _firmando = false),
          ),
        ]),
        if (_sinSenal)
          _Aviso(
            icono: Icons.signal_cellular_off,
            texto: 'Sin señal, el contrato no se crea. Todo lo de arriba ya '
                'quedó guardado en el teléfono: cuando tengas señal, toca '
                '«Crear el contrato». No se manda solo después, porque crear '
                'un cliente dos veces es peor que esperar.',
          ),
        _Boton(
          'Crear el contrato',
          Icons.task_alt,
          _hayFirma && !_sinSenal ? () => _ir(_Etapa.creando) : null,
        ),
        if (!_hayFirma)
          Text('Falta la firma del cliente.',
              textAlign: TextAlign.center, style: AppTypography.cuerpoChico),
      ]);

  Future<void> _cambiarServicio() async {
    final String? z = await showModalBottomSheet<String>(
      context: context,
      builder: (BuildContext c) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: <Widget>[
          const ListTile(title: Text('Zona / router')),
          for (final String o in <String>[
            'Soledad · Router Norte',
            'Soledad · Router Sur',
            'Barranquilla · Router Centro',
          ])
            ListTile(
              title: Text(o),
              trailing: o == _zona ? const Icon(Icons.check) : null,
              onTap: () => Navigator.of(c).pop(o),
            ),
        ]),
      ),
    );
    if (z == null) return;
    setState(() {
      _zona = z;
      _ip = z.contains('Sur')
          ? '10.20.9.12'
          : (z.contains('Centro') ? '10.10.2.88' : '10.20.5.47');
    });
  }

  // ------------------------------------------------------------------------
  //  6 · LISTO
  // ------------------------------------------------------------------------
  Widget _listo() => _Lista(children: <Widget>[
        _Tarjeta(children: <Widget>[
          const Icon(Icons.check_circle, color: AppColors.exito, size: 48),
          const SizedBox(height: 8),
          Text('Contrato creado', style: AppTypography.tituloGrande),
          const SizedBox(height: 4),
          Text('${_Solicitud.nombre} · Servicio #8421',
              style: AppTypography.cuerpo),
          const Divider(height: 24),
          const _Dato(icono: Icons.person_add_alt, texto: 'Cliente creado en WispHub'),
          const _Dato(icono: Icons.picture_as_pdf_outlined,
              texto: 'Contrato en PDF con la firma, en el expediente'),
          const _Dato(icono: Icons.confirmation_number_outlined,
              texto: 'Ticket «Instalación Nueva» cerrado'),
          const _Dato(icono: Icons.chat_outlined,
              texto: 'Bienvenida al cliente por WhatsApp'),
        ]),
        _Boton('Finalizar la orden', Icons.flag_outlined,
            () => _ir(_Etapa.asignada)),
      ]);
}

// ==========================================================================
//  LA CREACIÓN, PASO A PASO
// ==========================================================================
class _Creando extends StatefulWidget {
  const _Creando({required this.alTerminar});
  final VoidCallback alTerminar;

  @override
  State<_Creando> createState() => _EstadoCreando();
}

class _EstadoCreando extends State<_Creando> {
  static const List<List<String>> _pasos = <List<String>>[
    <String>['Crear el cliente en WispHub', 'Servicio #8421, plan y IP asignados'],
    <String>['Autorizar la ONU en SmartOLT', 'ZTEGC8F21A44 en el puerto 1/3/7'],
    <String>['Guardar el contrato firmado', 'PDF en el expediente del cliente'],
    <String>['Cerrar el ticket de instalación', 'Ticket #281 · Instalación Nueva'],
  ];
  int _hechos = 0;
  Timer? _reloj;

  @override
  void initState() {
    super.initState();
    _reloj = Timer.periodic(const Duration(milliseconds: 1100), (Timer t) {
      if (!mounted) return;
      setState(() => _hechos++);
      if (_hechos >= _pasos.length) {
        t.cancel();
        Future<void>.delayed(const Duration(milliseconds: 900), () {
          if (mounted) widget.alTerminar();
        });
      }
    });
  }

  @override
  void dispose() {
    _reloj?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => _Lista(children: <Widget>[
        Text('La plataforma lo hace por ti, sin salir de la app.',
            style: AppTypography.cuerpo),
        for (int i = 0; i < _pasos.length; i++)
          _Tarjeta(children: <Widget>[
            Row(children: <Widget>[
              SizedBox(
                width: 28,
                height: 28,
                child: i < _hechos
                    ? const Icon(Icons.check_circle, color: AppColors.exito)
                    : (i == _hechos
                        ? const Padding(
                            padding: EdgeInsets.all(4),
                            child: CircularProgressIndicator(strokeWidth: 2.5),
                          )
                        : const Icon(Icons.radio_button_unchecked,
                            color: AppColors.inactivo)),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(_pasos[i][0], style: AppTypography.tituloChico),
                    if (i < _hechos)
                      Text(_pasos[i][1], style: AppTypography.cuerpoChico),
                  ],
                ),
              ),
            ]),
          ]),
      ]);
}

// ==========================================================================
//  PIEZAS
// ==========================================================================
class _FranjaPrototipo extends StatelessWidget {
  const _FranjaPrototipo();

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        color: AppColors.precaucionFondo,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        child: Text(
          'PROTOTIPO · datos de ejemplo, no se envía nada',
          textAlign: TextAlign.center,
          style: AppTypography.etiquetaChica.copyWith(color: AppColors.precaucion),
        ),
      );
}

/// La línea de etapas de arriba: dónde va el técnico.
class _Pasos extends StatelessWidget {
  const _Pasos({required this.actual});
  final _Etapa actual;

  static const List<String> _nombres = <String>[
    'Asignada', 'En ruta', 'Instalando', 'Contrato', 'Listo',
  ];

  int get _indice => switch (actual) {
        _Etapa.asignada => 0,
        _Etapa.enRuta => 1,
        _Etapa.enSitio => 2,
        _Etapa.contrato || _Etapa.creando => 3,
        _Etapa.listo => 4,
      };

  @override
  Widget build(BuildContext context) => Container(
        color: AppColors.superficie,
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
        child: Row(children: <Widget>[
          for (int i = 0; i < _nombres.length; i++)
            Expanded(
              child: Column(children: <Widget>[
                CircleAvatar(
                  radius: 12,
                  backgroundColor: i < _indice
                      ? AppColors.exito
                      : (i == _indice ? AppColors.azulAccion : AppColors.inactivoFondo),
                  child: i < _indice
                      ? const Icon(Icons.check, size: 14, color: Colors.white)
                      : Text('${i + 1}',
                          style: TextStyle(
                              fontSize: 11,
                              color: i == _indice ? Colors.white : AppColors.inactivo)),
                ),
                const SizedBox(height: 4),
                Text(_nombres[i],
                    style: AppTypography.etiquetaChica.copyWith(
                        color: i == _indice ? AppColors.azulAccion : AppColors.textoSecundario)),
              ]),
            ),
        ]),
      );
}

class _Lista extends StatelessWidget {
  const _Lista({required this.children, this.fija = false});
  final List<Widget> children;
  final bool fija;

  @override
  Widget build(BuildContext context) => ListView(
        physics: fija ? const NeverScrollableScrollPhysics() : null,
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: <Widget>[
          for (final Widget w in children)
            Padding(padding: const EdgeInsets.only(bottom: 12), child: w),
        ],
      );
}

class _Tarjeta extends StatelessWidget {
  const _Tarjeta({required this.children, this.oscura = false});
  final List<Widget> children;
  final bool oscura;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: oscura ? AppColors.tintaProfunda : AppColors.superficie,
          borderRadius: AppRadius.brTarjeta,
          border: oscura ? null : Border.all(color: AppColors.borde),
        ),
        child: Column(
            crossAxisAlignment: CrossAxisAlignment.start, children: children),
      );
}

class _Dato extends StatelessWidget {
  const _Dato({required this.icono, required this.texto});
  final IconData icono;
  final String texto;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(children: <Widget>[
          Icon(icono, size: 18, color: AppColors.exito),
          const SizedBox(width: 8),
          Expanded(child: Text(texto, style: AppTypography.cuerpoChico)),
        ]),
      );
}

class _Boton extends StatelessWidget {
  const _Boton(this.texto, this.icono, this.alTocar);
  final String texto;
  final IconData icono;
  final VoidCallback? alTocar;

  @override
  Widget build(BuildContext context) => SizedBox(
        height: AppSpacing.objetivoTactilAmplio,
        child: FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: AppColors.azulAccion,
            shape: const RoundedRectangleBorder(borderRadius: AppRadius.brTarjeta),
          ),
          icon: Icon(icono),
          label: Text(texto, style: const TextStyle(fontSize: 17)),
          onPressed: alTocar,
        ),
      );
}

class _Paso extends StatelessWidget {
  const _Paso({
    required this.hecho,
    required this.titulo,
    required this.detalle,
    required this.accion,
    required this.alTocar,
    this.icono = Icons.edit_outlined,
  });
  final bool hecho;
  final String titulo;
  final String detalle;
  final String accion;
  final VoidCallback alTocar;
  final IconData icono;

  @override
  Widget build(BuildContext context) => _Tarjeta(children: <Widget>[
        Row(children: <Widget>[
          Icon(hecho ? Icons.check_circle : Icons.radio_button_unchecked,
              color: hecho ? AppColors.exito : AppColors.inactivo),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(titulo, style: AppTypography.tituloChico),
                Text(detalle, style: AppTypography.cuerpoChico),
              ],
            ),
          ),
          if (!hecho)
            OutlinedButton.icon(
              //  El tema de la app le da a los botones todo el ancho; dentro de
              //  una fila eso aplasta el texto. Acá va del tamaño del rótulo.
              style: OutlinedButton.styleFrom(
                minimumSize: const Size(0, 44),
                padding: const EdgeInsets.symmetric(horizontal: 12),
              ),
              icon: Icon(icono, size: 18),
              label: Text(accion),
              onPressed: alTocar,
            ),
        ]),
      ]);
}

/// Un grupo de datos del contrato, con un sello que dice DE DÓNDE salió: es lo
/// que le muestra al técnico qué no tiene que escribir.
class _Bloque extends StatelessWidget {
  const _Bloque({
    required this.titulo,
    required this.origen,
    required this.colorOrigen,
    required this.fondoOrigen,
    required this.filas,
    this.pie,
    this.accion,
    this.alAccion,
  });
  final String titulo;
  final String origen;
  final Color colorOrigen;
  final Color fondoOrigen;
  final List<List<String>> filas;
  final String? pie;
  final String? accion;
  final VoidCallback? alAccion;

  @override
  Widget build(BuildContext context) => _Tarjeta(children: <Widget>[
        Row(children: <Widget>[
          Text(titulo, style: AppTypography.tituloChico),
          const Spacer(),
          if (accion != null)
            TextButton(
              style: TextButton.styleFrom(minimumSize: const Size(0, 40)),
              onPressed: alAccion ?? () {},
              child: Text(accion!),
            ),
        ]),
        Container(
          margin: const EdgeInsets.only(top: 2, bottom: 10),
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
              color: fondoOrigen, borderRadius: AppRadius.brChico),
          child: Text(origen,
              style: AppTypography.etiquetaChica.copyWith(color: colorOrigen)),
        ),
        for (final List<String> f in filas)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                SizedBox(
                  width: 112,
                  child: Text(f[0], style: AppTypography.cuerpoChico),
                ),
                Expanded(child: Text(f[1], style: AppTypography.cuerpo)),
              ],
            ),
          ),
        if (pie != null) ...<Widget>[
          const SizedBox(height: 6),
          Text(pie!, style: AppTypography.etiquetaChica),
        ],
      ]);
}

class _Aviso extends StatelessWidget {
  const _Aviso({required this.icono, required this.texto});
  final IconData icono;
  final String texto;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
            color: AppColors.precaucionFondo, borderRadius: AppRadius.brTarjeta),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
          Icon(icono, color: AppColors.precaucion),
          const SizedBox(width: 10),
          Expanded(child: Text(texto, style: AppTypography.cuerpoChico)),
        ]),
      );
}

class _PadDeFirma extends StatelessWidget {
  const _PadDeFirma({
    required this.trazos,
    required this.alCambiar,
    required this.alEmpezar,
    required this.alTerminar,
  });
  final List<List<Offset?>> trazos;
  final VoidCallback alCambiar;
  final VoidCallback alEmpezar;
  final VoidCallback alTerminar;

  @override
  Widget build(BuildContext context) => Container(
        height: 150,
        decoration: BoxDecoration(
          color: AppColors.fondoHundido,
          borderRadius: AppRadius.brCampo,
          border: Border.all(color: AppColors.bordeFuerte),
        ),
        //  `Listener` y no `GestureDetector`: el desplazamiento de la pantalla
        //  le gana la disputa a un gesto de arrastre, y el trazo se perdía.
        //  El puntero crudo llega siempre, y al bajar el dedo se congela el
        //  scroll hasta levantarlo.
        child: Listener(
          onPointerDown: (PointerDownEvent e) {
            alEmpezar();
            trazos.add(<Offset?>[e.localPosition]);
            alCambiar();
          },
          onPointerMove: (PointerMoveEvent e) {
            if (trazos.isEmpty) return;
            trazos.last.add(e.localPosition);
            alCambiar();
          },
          onPointerUp: (_) => alTerminar(),
          onPointerCancel: (_) => alTerminar(),
          child: CustomPaint(
            painter: _Trazo(trazos),
            child: trazos.isEmpty
                ? Center(
                    child: Text('Firme aquí con el dedo',
                        style: AppTypography.cuerpoChico))
                : const SizedBox.expand(),
          ),
        ),
      );
}

class _Trazo extends CustomPainter {
  _Trazo(this.trazos);
  final List<List<Offset?>> trazos;

  @override
  void paint(Canvas canvas, Size size) {
    final Paint p = Paint()
      ..color = AppColors.texto
      ..strokeWidth = 2.6
      ..strokeCap = StrokeCap.round;
    for (final List<Offset?> t in trazos) {
      for (int i = 1; i < t.length; i++) {
        if (t[i - 1] != null && t[i] != null) canvas.drawLine(t[i - 1]!, t[i]!, p);
      }
    }
  }

  @override
  bool shouldRepaint(_Trazo old) => true;
}
