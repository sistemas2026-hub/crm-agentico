/// EL CONTRATO DEL CLIENTE, CREADO DESDE LA APP (13/11/2026).
///
/// Decisión del usuario: el técnico crea el contrato aquí y deja de llenarlo a
/// mano en WispHub. Los datos del cliente ya vienen de la solicitud que llenó;
/// el técnico los revisa con el documento delante, elige el servidor y el
/// cliente firma. El servidor arma el PDF (`campo/contrato.py`).
///
/// EXIGE SEÑAL, Y NO SE ENCOLA. Todo lo demás de esta app funciona sin red y
/// sube después. Esto no: es el primer paso del alta de un cliente, y un alta
/// que sale sola horas después, sin que nadie mire, puede crear un cliente
/// dos veces. Sin red la pantalla lo dice y el botón espera.
///
/// El alta en WispHub todavía no sale de aquí: el contrato queda «firmado» y la
/// pantalla lo dice. Ver SPEC/objetivos/agente-de-campo-para-instalaciones.md.
library;

import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_endpoints.dart';
import '../../core/storage/ubicacion_de_captura.dart';
import '../../core/theme/app_theme.dart';
import '../ejecucion/widgets/firma_del_cliente.dart';

/// Si esta orden es de las que llevan contrato.
///
/// La labor llega del servidor desde la v29 de la base local; las órdenes
/// bajadas antes no la tienen hasta que se vuelvan a leer, y por eso el código
/// de la plantilla sirve de respaldo.
bool llevaContrato(Map<String, dynamic>? orden) {
  if (orden == null) return false;
  if ((orden['labor'] ?? '').toString() == 'instalacion') return true;
  return (orden['tipo_codigo'] ?? '').toString().contains('instalacion');
}

/// Lo que el servidor contestó, traducido a lo que la pantalla necesita.
@immutable
class RespuestaDelServidor {
  const RespuestaDelServidor({this.cuerpo, this.error});
  final Map<String, dynamic>? cuerpo;
  final String? error;
}

/// Las dos llamadas. Reemplazable en pruebas.
class ApiDelContrato {
  const ApiDelContrato();

  static String _mensaje(Object e) {
    if (e is DioException) {
      final dynamic d = e.response?.data;
      if (d is Map && d['detail'] is String) return d['detail'] as String;
      if (e.response == null) {
        return 'Sin señal: el contrato no se creó. Toca otra vez cuando tengas señal.';
      }
      return 'El servidor no respondió bien (${e.response?.statusCode}). Intenta de nuevo.';
    }
    if (e is TimeoutException) {
      return 'Sin señal: el contrato no se creó. Toca otra vez cuando tengas señal.';
    }
    return 'No se pudo completar. Intenta de nuevo.';
  }

  Future<RespuestaDelServidor> leer(String ordenId) async {
    try {
      final Response<dynamic> r = await ApiClient()
          .get<dynamic>(ApiEndpoints.contratoDeLaOrden(ordenId))
          .timeout(const Duration(seconds: 15));
      final dynamic d = r.data is String ? jsonDecode(r.data as String) : r.data;
      return RespuestaDelServidor(cuerpo: Map<String, dynamic>.from(d as Map));
    } catch (e) {
      return RespuestaDelServidor(error: _mensaje(e));
    }
  }

  /// Las IP que se le pueden ofrecer en esa zona.
  ///
  /// NO devuelve error: una lista vacia con su motivo es una respuesta
  /// legitima --el servidor contesta 200 y explica por que no hay-- y el
  /// tecnico tiene que poder seguir firmando sin esto. El contrato no depende
  /// de la IP.
  Future<Map<String, dynamic>> ipsLibres(String ordenId, int idZona) async {
    try {
      final Response<dynamic> r = await ApiClient()
          .get<dynamic>(ApiEndpoints.ipsLibresDeLaOrden(ordenId, idZona))
          .timeout(const Duration(seconds: 15));
      final dynamic d = r.data is String ? jsonDecode(r.data as String) : r.data;
      return Map<String, dynamic>.from(d as Map);
    } catch (e) {
      return <String, dynamic>{
        'libres': const <dynamic>[],
        'motivo': 'No se pudieron consultar las direcciones disponibles.',
      };
    }
  }

  Future<RespuestaDelServidor> firmar(String ordenId, Map<String, dynamic> cuerpo) async {
    try {
      final Response<dynamic> r = await ApiClient()
          .post<dynamic>(ApiEndpoints.contratoDeLaOrden(ordenId), data: cuerpo)
          .timeout(const Duration(seconds: 40));
      final dynamic d = r.data is String ? jsonDecode(r.data as String) : r.data;
      return RespuestaDelServidor(cuerpo: Map<String, dynamic>.from(d as Map));
    } catch (e) {
      return RespuestaDelServidor(error: _mensaje(e));
    }
  }
}

class ContratoScreen extends StatefulWidget {
  const ContratoScreen({
    super.key,
    required this.ordenId,
    required this.titulo,
    this.api = const ApiDelContrato(),
  });

  final String ordenId;
  final String titulo;
  final ApiDelContrato api;

  @override
  State<ContratoScreen> createState() => _EstadoContrato();
}

/// Los campos del cliente, en el orden en que se muestran.
const List<List<String>> _camposDelCliente = <List<String>>[
  <String>['nombre', 'Nombre'],
  <String>['apellido', 'Apellido'],
  <String>['numero_documento', 'Documento'],
  <String>['telefono', 'Teléfono'],
  <String>['correo', 'Correo'],
  <String>['direccion', 'Dirección'],
  <String>['barrio', 'Barrio'],
];

class _EstadoContrato extends State<ContratoScreen> {
  bool _cargando = true;
  String? _errorDeCarga;
  Map<String, dynamic>? _contrato;
  Map<String, dynamic>? _borrador;
  List<Map<String, dynamic>> _servidores = <Map<String, dynamic>>[];
  int? _idZona;
  //  LAS IP DE LA ZONA ELEGIDA. Se piden recien cuando el tecnico elige el
  //  servidor, porque el servidor es lo que decide de que rango salen: es el
  //  mismo orden que el panel del ISP y el que la API del alta exige.
  List<String> _ips = <String>[];
  String? _ip;
  bool _cargandoIps = false;
  String _motivoSinIps = '';
  String _advertenciaIps = '';
  int _zonaDeLasIps = -1;
  bool _enviando = false;
  String? _errorDeEnvio;
  final TrazoDeFirma _trazo = TrazoDeFirma();
  final Map<String, TextEditingController> _campos = <String, TextEditingController>{};
  final TextEditingController _plan = TextEditingController();
  String _tipoDocumento = 'CC';

  @override
  void initState() {
    super.initState();
    _trazo.addListener(_redibujar);
    _cargar();
  }

  void _redibujar() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _trazo.removeListener(_redibujar);
    _trazo.dispose();
    for (final TextEditingController c in _campos.values) {
      c.dispose();
    }
    _plan.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    setState(() {
      _cargando = true;
      _errorDeCarga = null;
    });
    final RespuestaDelServidor r = await widget.api.leer(widget.ordenId);
    if (!mounted) return;
    if (r.error != null) {
      setState(() {
        _cargando = false;
        _errorDeCarga = r.error;
      });
      return;
    }
    final Map<String, dynamic> d = r.cuerpo!;
    setState(() {
      _cargando = false;
      _contrato = d['contrato'] is Map ? Map<String, dynamic>.from(d['contrato'] as Map) : null;
      _borrador = d['borrador'] is Map ? Map<String, dynamic>.from(d['borrador'] as Map) : null;
      _servidores = <Map<String, dynamic>>[
        for (final dynamic s in (d['servidores'] as List? ?? const <dynamic>[]))
          if (s is Map) Map<String, dynamic>.from(s),
      ];
      if (_servidores.length == 1) _idZona = _servidores.first['id_zona'] as int?;
      final Map<String, dynamic> cliente =
          Map<String, dynamic>.from((_borrador?['cliente'] as Map?) ?? const <String, dynamic>{});
      for (final List<String> c in _camposDelCliente) {
        _campos[c[0]] = TextEditingController(text: (cliente[c[0]] ?? '').toString());
      }
      _tipoDocumento = (cliente['tipo_documento'] ?? 'CC').toString();
      _plan.text = (_borrador?['plan'] ?? '').toString();
    });
    //  CON UN SOLO SERVIDOR LA ZONA SE ELIGE SOLA, y entonces nadie dispara
    //  `_pedirIps`: el `onChanged` del radio no corre. Es el caso mas comun
    //  --una empresa con un servidor-- y sin esto la pantalla quedaba con el
    //  servidor puesto y sin ninguna direccion que ofrecer.
    final int? zona = _idZona;
    if (zona != null && _contrato == null) await _pedirIps(zona);
  }

  /// Pide las libres de esa zona. No bloquea nada: si no hay, se dice.
  Future<void> _pedirIps(int idZona) async {
    setState(() {
      _cargandoIps = true;
      _zonaDeLasIps = idZona;
    });
    final Map<String, dynamic> d = await widget.api.ipsLibres(widget.ordenId, idZona);
    if (!mounted) return;
    //  LLEGO TARDE Y LA ZONA YA CAMBIO: se descarta. Sin esto, la respuesta
    //  de la zona vieja pisaria la lista de la nueva, y el tecnico elegiria
    //  una direccion de otro rango creyendo que es de la que marco.
    if (_zonaDeLasIps != idZona) return;
    setState(() {
      _cargandoIps = false;
      _ips = <String>[
        for (final dynamic x in (d['libres'] as List? ?? const <dynamic>[]))
          if (x.toString().trim().isNotEmpty) x.toString(),
      ];
      _motivoSinIps = _ips.isEmpty ? (d['motivo'] ?? '').toString() : '';
      _advertenciaIps = (d['advertencia'] ?? '').toString();
    });
  }

  bool get _listo =>
      !_trazo.vacio &&
      _idZona != null &&
      (_campos['nombre']?.text.trim().isNotEmpty ?? false) &&
      (_campos['numero_documento']?.text.trim().isNotEmpty ?? false) &&
      (_campos['direccion']?.text.trim().isNotEmpty ?? false) &&
      _plan.text.trim().isNotEmpty;

  Future<void> _crear() async {
    setState(() {
      _enviando = true;
      _errorDeEnvio = null;
    });
    final List<int> firma = await _trazo.aPng(const Size(600, 300));
    //  Dónde se firmó: el punto real de la casa. Nunca tarda más de su plazo
    //  ni lanza (ver `UbicacionDeCaptura`).
    final Map<String, dynamic> ubicacion = await UbicacionDeCaptura.tomar();
    final Map<String, dynamic> cuerpo = <String, dynamic>{
      'cliente': <String, dynamic>{
        for (final List<String> c in _camposDelCliente) c[0]: _campos[c[0]]!.text.trim(),
        'tipo_documento': _tipoDocumento,
      },
      'plan': _plan.text.trim(),
      'id_zona': _idZona,
      //  Si no eligio ninguna, no viaja: el servidor acepta vacio porque
      //  una empresa sin pools declarados tiene que poder firmar igual.
      if (_ip != null) 'ip': _ip,
      'firma_png_base64': base64Encode(firma),
      if (ubicacion.containsKey('lat') && ubicacion.containsKey('lng'))
        'gps': <String, dynamic>{
          'lat': ubicacion['lat'],
          'lng': ubicacion['lng'],
          'precision_m': ubicacion['precision_m'],
        },
    };
    final RespuestaDelServidor r = await widget.api.firmar(widget.ordenId, cuerpo);
    if (!mounted) return;
    setState(() {
      _enviando = false;
      if (r.error != null) {
        _errorDeEnvio = r.error;
      } else if (r.cuerpo?['contrato'] is Map) {
        _contrato = Map<String, dynamic>.from(r.cuerpo!['contrato'] as Map);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.fondo,
      appBar: AppBar(title: Text('Contrato · ${widget.titulo}')),
      body: SafeArea(child: _cuerpo()),
    );
  }

  Widget _cuerpo() {
    if (_cargando) return const Center(child: CircularProgressIndicator());
    if (_errorDeCarga != null) {
      return _Centro(
        icono: Icons.signal_cellular_connected_no_internet_4_bar,
        titulo: 'Necesitas señal para el contrato',
        texto: _errorDeCarga!,
        accion: 'Reintentar',
        alTocar: _cargar,
      );
    }
    if (_contrato != null) return _firmado(_contrato!);
    return _formulario();
  }

  Widget _firmado(Map<String, dynamic> c) {
    final Map<String, dynamic> cliente =
        Map<String, dynamic>.from((c['cliente'] as Map?) ?? const <String, dynamic>{});
    final Map<String, dynamic> servidor =
        Map<String, dynamic>.from((c['servidor'] as Map?) ?? const <String, dynamic>{});
    return ListView(
      padding: const EdgeInsets.all(16),
      children: <Widget>[
        _Tarjeta(children: <Widget>[
          const Icon(Icons.check_circle, color: AppColors.exito, size: 44),
          const SizedBox(height: 8),
          Text('Contrato firmado', style: AppTypography.tituloGrande),
          Text('N.º ${c['numero']}', style: AppTypography.cuerpo),
          const Divider(height: 24),
          _Fila('Cliente', '${cliente['nombre'] ?? ''} ${cliente['apellido'] ?? ''}'.trim()),
          _Fila('Documento',
              '${cliente['tipo_documento'] ?? ''} ${cliente['numero_documento'] ?? ''}'.trim()),
          _Fila('Plan', (c['plan'] ?? '').toString()),
          _Fila('Servidor', (servidor['nombre'] ?? '').toString()),
          const SizedBox(height: 10),
          Text('El PDF con la firma quedó en la plataforma.',
              style: AppTypography.cuerpoChico),
        ]),
        if (c['estado'] != 'en_el_isp')
          const _Aviso(
            icono: Icons.schedule,
            texto: 'El cliente todavía no se crea en WispHub desde aquí. '
                'Esa parte se está terminando; mientras tanto la oficina lo da '
                'de alta con estos datos.',
          ),
      ],
    );
  }

  Widget _formulario() {
    final bool deSolicitud = _borrador?['origen'] == 'solicitud';
    final Map<String, dynamic>? aut = _borrador?['autorizaciones'] is Map
        ? Map<String, dynamic>.from(_borrador!['autorizaciones'] as Map)
        : null;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
      children: <Widget>[
        _Tarjeta(children: <Widget>[
          Text('El cliente', style: AppTypography.tituloChico),
          _Sello(
            texto: deSolicitud
                ? 'Lo llenó el cliente en la solicitud. Revísalo con el documento.'
                : 'Sin solicitud: llénalo con el documento a la vista.',
            ok: deSolicitud,
          ),
          for (final List<String> c in _camposDelCliente)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: TextField(
                controller: _campos[c[0]],
                onChanged: (_) => setState(() {}),
                keyboardType: c[0] == 'telefono' || c[0] == 'numero_documento'
                    ? TextInputType.number
                    : (c[0] == 'correo' ? TextInputType.emailAddress : TextInputType.text),
                decoration: InputDecoration(
                  labelText: c[1],
                  prefixText: c[0] == 'numero_documento' ? '$_tipoDocumento ' : null,
                  isDense: true,
                  border: const OutlineInputBorder(),
                ),
              ),
            ),
          if (aut != null)
            Text(
              '${aut['habeas_data'] == true ? '☑' : '☐'} Habeas data   '
              '${aut['centrales_de_riesgo'] == true ? '☑' : '☐'} Centrales de riesgo',
              style: AppTypography.cuerpoChico,
            ),
        ]),
        _Tarjeta(children: <Widget>[
          Text('El servicio', style: AppTypography.tituloChico),
          const SizedBox(height: 8),
          TextField(
            controller: _plan,
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(
                labelText: 'Plan', isDense: true, border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          Text('Servidor', style: AppTypography.etiqueta),
          if (_servidores.isEmpty)
            const _Aviso(
              icono: Icons.info_outline,
              texto: 'Tu empresa no ha cargado sus servidores en la plataforma '
                  '(Programación → El contrato de instalación).',
            ),
          RadioGroup<int>(
            groupValue: _idZona,
            onChanged: (int? v) {
              setState(() {
                _idZona = v;
                //  La IP de la zona anterior no sirve para la nueva: se
                //  suelta. Dejarla puesta seria ofrecer una direccion de
                //  otro rango sin que nadie lo note.
                _ip = null;
                _ips = <String>[];
                _motivoSinIps = '';
              });
              if (v != null) _pedirIps(v);
            },
            //  Material transparente: sin él, la tarjeta de color tapa el
            //  efecto del toque y el técnico no ve que eligió.
            child: Material(
              type: MaterialType.transparency,
              child: Column(children: <Widget>[
                for (final Map<String, dynamic> s in _servidores)
                  RadioListTile<int>(
                    contentPadding: EdgeInsets.zero,
                    value: s['id_zona'] as int,
                    title: Text((s['nombre'] ?? '').toString()),
                  ),
              ]),
            ),
          ),
          //  LA IP, DESPUES DEL SERVIDOR  --  14/11/2026
          //
          //  Se OFRECE y no se teclea, que es el motivo de todo esto: el
          //  usuario reporto que al digitar los datos «hay muchos errores».
          //  Una IP mal tecleada no es un error de ortografia: es un cliente
          //  sin servicio, o dos clientes con la misma IP.
          if (_idZona != null) ...<Widget>[
            const SizedBox(height: 12),
            Text('Dirección IP', style: AppTypography.etiqueta),
            if (_cargandoIps)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Row(children: <Widget>[
                  SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2)),
                  SizedBox(width: 8),
                  Text('Buscando las disponibles...'),
                ]),
              )
            else if (_ips.isEmpty)
              _Aviso(
                icono: Icons.info_outline,
                texto: _motivoSinIps.isEmpty
                    ? 'No hay direcciones para ofrecer en este servidor.'
                    : _motivoSinIps,
              )
            else ...<Widget>[
              //  Un Wrap y no un RadioGroup: son veinte opciones cortas y en
              //  columna no caben en una pantalla de telefono.
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: <Widget>[
                  for (final String ip in _ips)
                    ChoiceChip(
                      label: Text(ip),
                      selected: _ip == ip,
                      onSelected: (bool sel) => setState(() => _ip = sel ? ip : null),
                    ),
                ],
              ),
              if (_advertenciaIps.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  //  LA ADVERTENCIA SE MUESTRA, no se guarda en el codigo: una
                  //  direccion libre aqui es una que ningun CLIENTE tiene. Las
                  //  antenas y los switches no son clientes.
                  child: _Aviso(icono: Icons.warning_amber_outlined,
                      texto: _advertenciaIps),
                ),
            ],
          ],
        ]),
        _Tarjeta(children: <Widget>[
          Row(children: <Widget>[
            //  Expanded y no Spacer: con letra grande, el título y «Borrar»
            //  no cabían juntos y la fila se desbordaba (lo vio la prueba).
            Expanded(child: Text('Firma del cliente', style: AppTypography.tituloChico)),
            if (!_trazo.vacio)
              TextButton(
                style: TextButton.styleFrom(minimumSize: const Size(0, 40)),
                onPressed: _trazo.limpiar,
                child: const Text('Borrar'),
              ),
          ]),
          Text('Acepta el contrato y la instalación recibida.',
              style: AppTypography.cuerpoChico),
          const SizedBox(height: 8),
          Container(
            height: 180,
            decoration: BoxDecoration(
              color: AppColors.fondoHundido,
              borderRadius: AppRadius.brCampo,
              border: Border.all(color: AppColors.bordeFuerte),
            ),
            child: ClipRRect(
              borderRadius: AppRadius.brCampo,
              child: Stack(children: <Widget>[
                if (_trazo.vacio)
                  Center(child: Text('Firme aquí con el dedo', style: AppTypography.cuerpoChico)),
                Positioned.fill(child: LienzoDeFirma(trazo: _trazo)),
              ]),
            ),
          ),
        ]),
        if (_errorDeEnvio != null)
          _Aviso(icono: Icons.error_outline, texto: _errorDeEnvio!),
        SizedBox(
          height: AppSpacing.objetivoTactilAmplio,
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.azulAccion,
              shape: const RoundedRectangleBorder(borderRadius: AppRadius.brTarjeta),
            ),
            icon: _enviando
                ? const SizedBox(
                    width: 18, height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.task_alt),
            //  Corto y con elipsis: con letra grande o pantalla angosta,
            //  «Creando el contrato…» no cabía al lado del indicador.
            label: Text(_enviando ? 'Creando…' : 'Crear el contrato',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 17)),
            onPressed: _listo && !_enviando ? _crear : null,
          ),
        ),
        if (!_listo && !_enviando)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_queFalta(), textAlign: TextAlign.center,
                style: AppTypography.cuerpoChico),
          ),
      ],
    );
  }

  String _queFalta() {
    final List<String> f = <String>[
      if (_campos['nombre']?.text.trim().isEmpty ?? true) 'el nombre',
      if (_campos['numero_documento']?.text.trim().isEmpty ?? true) 'el documento',
      if (_campos['direccion']?.text.trim().isEmpty ?? true) 'la dirección',
      if (_plan.text.trim().isEmpty) 'el plan',
      if (_idZona == null) 'el servidor',
      if (_trazo.vacio) 'la firma del cliente',
    ];
    return f.isEmpty ? '' : 'Falta ${f.join(', ')}.';
  }
}

// ==========================================================================
//  PIEZAS
// ==========================================================================
class _Tarjeta extends StatelessWidget {
  const _Tarjeta({required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.superficie,
          borderRadius: AppRadius.brTarjeta,
          border: Border.all(color: AppColors.borde),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
      );
}

class _Sello extends StatelessWidget {
  const _Sello({required this.texto, required this.ok});
  final String texto;
  final bool ok;

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(top: 4, bottom: 12),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: ok ? AppColors.exitoFondo : AppColors.precaucionFondo,
          borderRadius: AppRadius.brChico,
        ),
        child: Text(texto,
            style: AppTypography.etiquetaChica
                .copyWith(color: ok ? AppColors.exitoTexto : AppColors.precaucion)),
      );
}

class _Fila extends StatelessWidget {
  const _Fila(this.rotulo, this.valor);
  final String rotulo;
  final String valor;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
          SizedBox(width: 100, child: Text(rotulo, style: AppTypography.cuerpoChico)),
          Expanded(child: Text(valor, style: AppTypography.cuerpo)),
        ]),
      );
}

class _Aviso extends StatelessWidget {
  const _Aviso({required this.icono, required this.texto});
  final IconData icono;
  final String texto;

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(bottom: 12, top: 4),
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

class _Centro extends StatelessWidget {
  const _Centro({
    required this.icono,
    required this.titulo,
    required this.texto,
    required this.accion,
    required this.alTocar,
  });
  final IconData icono;
  final String titulo;
  final String texto;
  final String accion;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: <Widget>[
            Icon(icono, size: 48, color: AppColors.textoSecundario),
            const SizedBox(height: 12),
            Text(titulo, style: AppTypography.tituloMedio, textAlign: TextAlign.center),
            const SizedBox(height: 6),
            Text(texto, style: AppTypography.cuerpo, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            OutlinedButton(onPressed: alTocar, child: Text(accion)),
          ]),
        ),
      );
}
