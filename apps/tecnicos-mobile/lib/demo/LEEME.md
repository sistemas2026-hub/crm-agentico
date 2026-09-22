# Esto NO es producto

Todo lo que hay en esta carpeta son **valores de ejemplo**: datos que el diseño
muestra y que ningún sistema de Dexter entrega todavía.

Vivía en `lib/core/mock/`. Se movió acá porque `core/` es el núcleo de la
aplicación, y un dato de ejemplo con esa dirección se lee como infraestructura:
dentro de seis meses alguien abre `FieldMockData.vehiculoPlaca` y concluye que
el módulo de vehículos existe.

## Las tres reglas

1. **Nada de acá decide.** No habilita un botón, no filtra, no ordena, no cambia
   un estado y no dispara una alerta. Sólo se muestra.
2. **Nada de acá inventa trabajo.** Puede completar un campo futuro de una orden
   que existe; jamás agrega una orden, un aviso o una tarea.
3. **Fuera del modo demostración no llega a pantalla.** Quien está en la calle no
   puede confundir un valor de ejemplo con la señal real de la casa donde está
   parado.

La regla 3 se mide, no se declara: `test/guarda_demo_test.dart` monta las
pantallas en las dos compilaciones y afirma lo contrario en cada una. Corre en
las dos antes de dar por bueno un cambio acá:

```
flutter test test/guarda_demo_test.dart
flutter test test/guarda_demo_test.dart --dart-define=DEXTER_DEMO=true
```

Una guarda que sólo corre apagada no prueba nada: si el bloque no se dibujaba
por otro motivo, la prueba pasa sin haber mirado. Ya pasó dos veces.

## No borrar

Cada constante lleva un identificador `CAMPO-DATA-XXX` y es la especificación
de lo que falta construir. El inventario completo, con su fuente prevista, está
en `docs/campo_datos_pendientes.md`. Borrar el fixture no salda la deuda: la
esconde.
