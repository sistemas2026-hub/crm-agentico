import 'package:flutter_test/flutter_test.dart';
import 'package:campo/main.dart';

void main() {
  testWidgets('Smoke test inicial de la aplicación Dexter Campo', (WidgetTester tester) async {
    await tester.pumpWidget(const DexterCampoApp(hasValidSession: false));
    await tester.pumpAndSettle();

    expect(find.text('DEXTER IA'), findsOneWidget);
    expect(find.text('INGRESAR AL SISTEMA'), findsOneWidget);
  });
}
