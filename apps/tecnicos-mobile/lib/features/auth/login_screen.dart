import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import '../../core/api/api_client.dart';
import '../../core/api/api_endpoints.dart';
import '../../core/storage/ciclo_de_vida_local.dart';
import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../shell/app_shell.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  /// Lo escrito, si es una dirección a la que se le puede pedir algo.
  ///
  /// Devuelve `null` cuando no lo es. Vale la pena ser estricto: el campo se
  /// tipea con el pulgar, a veces al sol, y una dirección a medias no falla
  /// al escribirla sino un rato después, como un "error de conexión" que no
  /// se parece en nada a su causa. Mejor decirlo acá.
  static String? normalizarServidor(String crudo) {
    final texto = crudo.trim();
    if (texto.isEmpty) return null;
    final Uri? url = Uri.tryParse(texto);
    if (url == null) return null;
    if (url.scheme != 'http' && url.scheme != 'https') return null;
    if (url.host.isEmpty || !url.host.contains('.')) return null;
    // Una ruta, ahi, no es un servidor.
    //
    // `ApiEndpoints` arma `'$baseUrl/api/...'`, asi que lo unico que se
    // espera es esquema, dominio y puerto. Si viene algo mas, se rechaza en
    // vez de recortarlo: recortar en silencio convierte texto pegado encima
    // de otro -- `https://uno.cohttps://dos.co`, que parsea como el dominio
    // `uno.cohttps` con una ruta -- en una direccion que parece buena y no
    // resuelve. Eso mismo paso en el emulador. Una barra final sola si se
    // acepta, porque escribirla es normal y no cambia a donde se va.
    if (url.path.isNotEmpty && url.path != '/') return null;
    if (url.hasQuery || url.hasFragment) return null;
    return Uri(scheme: url.scheme, host: url.host, port: url.hasPort ? url.port : null)
        .toString();
  }

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController(
    text: kDebugMode ? 'carlos.tecnico@rapilink.com' : '',
  );
  final _passwordController = TextEditingController();
  // El servidor al que se va a entrar.
  //
  // Arranca con el valor de compilación (`--dart-define=BACKEND_URL=...`) y
  // en `initState` se reemplaza por el que haya elegido esta persona, si
  // eligió alguno. Lo elegido sobrevive a cerrar la aplicación y a cerrar
  // sesión: se cambia acá, o con el botón de restablecer.
  final _serverUrlController = TextEditingController(
    text: ApiEndpoints.defaultEnvironmentUrl,
  );

  final _storage = SecureStorageService();
  final _apiClient = ApiClient();
  final _syncService = SyncQueueService();

  bool _isLoading = false;
  bool _showPassword = false;
  bool _mostrarServidor = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    // La línea de arriba y el campo son el MISMO dato, así que se mueven
    // juntos. Sin esto quedaban diciendo servidores distintos al mismo
    // tiempo: el campo ya decía el nuevo y el encabezado seguía mostrando el
    // anterior, que es la peor versión posible de una pantalla cuya única
    // razón de ser es no dejar dudas sobre a dónde va la contraseña.
    _serverUrlController.addListener(_alEscribirElServidor);
    _cargarServidorGuardado();
    _checkExistingSession();
  }

  @override
  void dispose() {
    _serverUrlController.removeListener(_alEscribirElServidor);
    super.dispose();
  }

  void _alEscribirElServidor() {
    if (mounted) setState(() {});
  }

  /// Muestra a dónde apunta hoy la aplicación, no a dónde apuntaba de fábrica.
  Future<void> _cargarServidorGuardado() async {
    final guardado = await _storage.getBaseUrl();
    if (!mounted) return;
    setState(() => _serverUrlController.text = guardado);
  }

  /// El servidor, en la forma corta que sirve para reconocerlo de un vistazo.
  String _servidorActual() {
    final texto = _serverUrlController.text.trim();
    if (texto.isEmpty) return 'Servidor sin definir';
    final String? valido = LoginScreen.normalizarServidor(texto);
    if (valido == null) return 'Dirección no válida';
    return Uri.parse(valido).host;
  }

  /// Vuelve al servidor con el que se compiló esta copia.
  ///
  /// Es la salida cuando alguien escribió cualquier cosa y ya no sabe cuál
  /// era el bueno: un técnico en la calle no tiene a quién preguntarle.
  Future<void> _restablecerServidor() async {
    await _storage.setBaseUrl(ApiEndpoints.defaultEnvironmentUrl);
    if (!mounted) return;
    setState(() {
      _serverUrlController.text = ApiEndpoints.defaultEnvironmentUrl;
      _errorMessage = null;
    });
  }

  Future<void> _checkExistingSession() async {
    final hasSession = await _storage.hasValidSession();
    if (hasSession && mounted) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => AppShell()),
      );
    }
  }

  Future<void> _handleLogin() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      // Se entra al servidor que dice la pantalla, siempre. Antes esto era
      // así sólo en depuración y en release se ignoraba el campo: un APK
      // compilado apuntando al servidor equivocado no se podía corregir sin
      // volver a compilar e instalar en cada teléfono.
      final String escrito = _serverUrlController.text.trim();
      final String? baseUrl = escrito.isEmpty
          ? ApiEndpoints.defaultEnvironmentUrl
          : LoginScreen.normalizarServidor(escrito);
      if (baseUrl == null) {
        setState(() {
          _isLoading = false;
          _mostrarServidor = true;
          _errorMessage = 'La dirección del servidor no es válida. Tiene que '
              'empezar con https:// y terminar en un dominio, como '
              'https://ejemplo.com';
        });
        return;
      }
      await _storage.setBaseUrl(baseUrl);

      final response = await _apiClient.post(
        ApiEndpoints.login,
        data: {
          'email': _emailController.text.trim(),
          'password': _passwordController.text,
        },
      );

      dynamic rawData = response.data;
      if (rawData is String) {
        try {
          rawData = jsonDecode(rawData);
        } catch (_) {}
      }

      if (response.statusCode == 200 && rawData is Map) {
        final data = Map<String, dynamic>.from(rawData);
        final accessToken = data['access_token'] ?? data['access'];
        final refreshToken = data['refresh_token'] ?? data['refresh'];
        final currentOrg = data['current_org'] is Map ? data['current_org'] : {};
        final user = data['user'] is Map ? data['user'] : {};

        // La identidad sale SIEMPRE de la respuesta del servidor, nunca de
        // algo que el teléfono pueda elegir: es la que particiona todo lo que
        // se guarda localmente.
        //
        // Y sin valores de relleno. Antes, una respuesta sin organización
        // caía en una organización inventada y una sin perfil en un perfil
        // inventado: dos personas distintas en esa situación compartían una
        // misma partición ficticia, y una veía las órdenes de la otra. Justo
        // el agujero que el resto de este trabajo cierra. Más abajo se
        // rechaza el ingreso si falta alguno de los dos.
        final orgId = currentOrg['id']?.toString() ?? '';
        final orgName = currentOrg['name']?.toString() ?? 'Organización';
        final email = user['email']?.toString() ?? _emailController.text.trim();
        String profileId = user['profile_id']?.toString() ?? user['id']?.toString() ?? '';
        String name = user['name']?.toString() ?? 'Carlos Técnico';

        // 1. Guardar tokens de autenticación
        await _storage.saveTokens(
          accessToken: accessToken,
          refreshToken: refreshToken,
        );

        // 2. Invocar bootstrap para obtener el profile_id de campo y capacidades
        try {
          final bootRes = await _apiClient.get(ApiEndpoints.bootstrap);
          dynamic bootData = bootRes.data;
          if (bootData is String) {
            try {
              bootData = jsonDecode(bootData);
            } catch (_) {}
          }
          if (bootRes.statusCode == 200 && bootData is Map) {
            final u = bootData['usuario'] is Map ? bootData['usuario'] : {};
            if (u['id'] != null) profileId = u['id'].toString();
            if (u['nombre'] != null) name = u['nombre'].toString();
          }
        } catch (_) {}

        // Fail-closed: sin identidad completa no se entra.
        //
        // Sin organización no hay órdenes que ver -- todo el backend filtra
        // por ella -- así que entrar igual solo serviría para dejar datos
        // bajo una identidad que no identifica a nadie. Se cierra la sesión
        // que se acababa de abrir para no dejar tokens sueltos.
        if (orgId.isEmpty || profileId.isEmpty) {
          await _storage.clearSession();
          if (mounted) {
            setState(() {
              _isLoading = false;
              _errorMessage = 'Tu cuenta entró, pero no tiene una organización '
                  'ni un perfil activos. Pedile a un administrador que te '
                  'asigne uno antes de volver a intentar.';
            });
          }
          return;
        }

        await _storage.saveSessionData(
          orgId: orgId,
          orgName: orgName,
          profileId: profileId,
          email: email,
          name: name,
        );

        // 3. Dejar el teléfono limpio de lo que no es de quien acaba de entrar.
        //
        // Un teléfono de cuadrilla pasa de mano en mano. Lo que dejó la cuenta
        // anterior no se puede mostrar acá -- el filtro por identidad ya lo
        // impide -- pero tampoco tiene por qué seguir en el disco: son nombres,
        // direcciones y fotos de casas de clientes.
        //
        // Lo único que sobrevive es el trabajo ajeno SIN SUBIR. Ese no se
        // borra: no es de quien entra, así que no lo ve, pero destruirlo
        // tampoco le corresponde a esta pantalla. Vuelve cuando esa cuenta
        // entre de nuevo.
        try {
          final limpieza = await CicloDeVidaLocal(LocalDatabase()).prepararPara(
            orgId: orgId,
            profileId: profileId,
          );
          if (limpieza.hayTrabajoAjenoRetenido) {
            debugPrint(
              '[sesion] se conservaron datos sin sincronizar de '
              '${limpieza.aisladas.length} cuenta(s) anterior(es) en este equipo.',
            );
          }
        } catch (e) {
          // Que la limpieza falle no puede impedir entrar a trabajar: se
          // reintenta en el próximo inicio de sesión.
          debugPrint('[sesion] no se pudo preparar el almacenamiento local: $e');
        }

        // 4. Descargar órdenes iniciales
        await _syncService.procesarCola();

        if (mounted) {
          Navigator.of(context).pushReplacement(
            MaterialPageRoute(builder: (_) => AppShell()),
          );
        }
      } else {
        setState(() {
          _errorMessage = 'Credenciales no válidas.';
        });
      }
    } on DioException catch (dioErr) {
      String? serverDetail;
      if (dioErr.response?.data is Map) {
        serverDetail = dioErr.response?.data['detail']?.toString() ??
            dioErr.response?.data['error']?.toString();
      } else if (dioErr.response?.data != null) {
        serverDetail = dioErr.response?.data.toString();
      }
      setState(() {
        if (serverDetail != null && serverDetail.isNotEmpty) {
          _errorMessage = serverDetail;
        } else if (dioErr.response?.statusCode == 401 || dioErr.response?.statusCode == 400) {
          _errorMessage = 'Email o contraseña incorrectos.';
        } else {
          _errorMessage = 'Error de conexión: ${dioErr.message}';
        }
      });
    } catch (e) {
      setState(() {
        _errorMessage = 'Error inesperado: $e';
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(
                    Icons.handyman_rounded,
                    size: 64,
                    color: AppTheme.primaryBlue,
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'DEXTER IA',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 26,
                      fontWeight: FontWeight.w900,
                      color: AppTheme.primaryDark,
                      letterSpacing: 1.5,
                    ),
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'Operaciones y Cuadrillas en Terreno',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 14,
                      color: AppTheme.textMuted,
                    ),
                  ),
                  const SizedBox(height: 32),
                  if (_errorMessage != null) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppTheme.errorRed.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: AppTheme.errorRed.withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline, color: AppTheme.errorRed, size: 20),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              _errorMessage!,
                              style: const TextStyle(color: AppTheme.errorRed, fontSize: 13),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  // A qué servidor se está por entrar.
                  //
                  // POR QUÉ SE VE SIEMPRE, Y NO SÓLO EN DEPURACIÓN
                  // ----------------------------------------------
                  // Antes esto existía únicamente en las compilaciones de
                  // desarrollo. En un APK de release el servidor quedaba fijo
                  // al compilar y no había forma de corregirlo desde el
                  // teléfono: si se equivocaban al armar el artefacto, o si
                  // el dominio cambiaba, la única salida era recompilar e
                  // reinstalar en cada teléfono.
                  //
                  // Ahora se puede cambiar. Va plegado y en letra chica a
                  // propósito: quien entra todos los días no tiene que verlo
                  // ni tocarlo, pero quien lo necesita lo encuentra.
                  //
                  // Y va **siempre visible** aunque esté plegado, porque
                  // dejar que alguien escriba su contraseña sin saber a qué
                  // servidor la manda es el riesgo real de tener esto acá.
                  // La línea dice a dónde apunta, sin abrir nada.
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      onPressed: _isLoading
                          ? null
                          : () => setState(
                              () => _mostrarServidor = !_mostrarServidor),
                      icon: Icon(
                        _mostrarServidor
                            ? Icons.expand_less
                            : Icons.dns_outlined,
                        size: 16,
                      ),
                      label: Text(
                        _servidorActual(),
                        style: const TextStyle(fontSize: 12),
                      ),
                    ),
                  ),
                  if (_mostrarServidor) ...[
                    const SizedBox(height: 8),
                    TextFormField(
                      controller: _serverUrlController,
                      enabled: !_isLoading,
                      keyboardType: TextInputType.url,
                      autocorrect: false,
                      decoration: InputDecoration(
                        labelText: 'Servidor',
                        prefixIcon: const Icon(Icons.dns_outlined),
                        helperText: 'Se recuerda en este teléfono hasta que '
                            'lo cambies o lo restablezcas.',
                        helperMaxLines: 2,
                        suffixIcon: IconButton(
                          tooltip: 'Volver al servidor de fábrica',
                          icon: const Icon(Icons.restart_alt, size: 20),
                          onPressed: _isLoading ? null : _restablecerServidor,
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  TextFormField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: 'Correo electrónico',
                      prefixIcon: Icon(Icons.email_outlined),
                    ),
                    validator: (value) =>
                        value == null || value.isEmpty ? 'Ingrese su correo' : null,
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _passwordController,
                    obscureText: !_showPassword,
                    decoration: InputDecoration(
                      labelText: 'Contraseña',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(
                          _showPassword ? Icons.visibility_off : Icons.visibility,
                        ),
                        onPressed: () {
                          setState(() {
                            _showPassword = !_showPassword;
                          });
                        },
                      ),
                    ),
                    validator: (value) =>
                        value == null || value.isEmpty ? 'Ingrese su contraseña' : null,
                  ),
                  const SizedBox(height: 24),
                  ElevatedButton(
                    onPressed: _isLoading ? null : _handleLogin,
                    child: _isLoading
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(
                              color: Colors.white,
                              strokeWidth: 2,
                            ),
                          )
                        : const Text('INGRESAR AL SISTEMA'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
