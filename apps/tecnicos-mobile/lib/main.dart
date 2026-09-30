import 'package:flutter/material.dart';
import 'core/storage/secure_storage_service.dart';
import 'core/theme/app_theme.dart';
import 'features/auth/login_screen.dart';
import 'features/jornada/jornada_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final storage = SecureStorageService();
  final hasSession = await storage.hasValidSession();

  runApp(DexterCampoApp(hasValidSession: hasSession));
}

class DexterCampoApp extends StatelessWidget {
  final bool hasValidSession;

  const DexterCampoApp({super.key, required this.hasValidSession});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Dexter IA',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      home: hasValidSession ? const JornadaScreen() : const LoginScreen(),
    );
  }
}
