# Deuda de las pruebas de la app de campo

Fallas conocidas que NO bloquean, con lo que se midió de cada una. Están acá
para que quien se las encuentre no empiece de cero, y para que nadie las
"arregle" a ciegas.

---

## E2E-002 falla una vez cada tanto, y no se pudo reproducir (24/09/2026)

```
Failing tests:
  test/e2e_002_trabajo_sin_materiales_test.dart:
    E2E-002 · Trabajo sin materiales 1. Se abre y pide sólo lo que la plantilla pide
```

**Qué se midió**, en este orden:

| Intento | Resultado |
|---|---|
| Suite completa, máquina cargada (86 s) | **falla** (558 +1 ~1 −1) |
| El archivo solo | pasa (4/4) |
| Con e2e_003 y e2e_004, tres corridas | pasa (16/16 cada una) |
| Suite completa, máquina libre (26 s) | pasa (559) |
| Suite completa con `--concurrency=12`, dos corridas | pasa (559 las dos) |

**Lo que se descartó, no lo que se supuso:**

- **No es colisión de base.** Los 18 archivos que usan `LocalDatabase` fijan
  cada uno la suya con `usarBaseDePruebas`, y los tres E2E usan
  `e2e_002.db`, `e2e_003.db` y `e2e_004.db`. Se verificó uno por uno.
- **No es un archivo nuevo.** La falla apareció al sumar
  `senal_optica_ot_test.dart`, pero ese archivo no toca `LocalDatabase` ni
  comparte nada: lo único que cambió fue el reparto en paralelo. Sin él la
  suite daba 551 y cero fallas; con él, 559 y una falla **esa vez**, y 559 y
  cero fallas las cuatro veces siguientes.

**Lo que queda**: sensibilidad a la carga de la máquina. Es la explicación que
mejor se sostiene con lo medido —falló solo en la corrida más lenta, casi tres
veces más lenta que las demás— y **no está probada**.

**Por qué no se arregló.** No se pudo reproducir en cuatro intentos, así que
cualquier cambio sería sobre una hipótesis sin medir. Escribir un arreglo que
no se puede ver fallar primero es el error que este repositorio ya documentó
tres veces: una prueba que afirma que un mecanismo existe no prueba que
funcione.

**Qué hacer si vuelve a aparecer**: pegar el mensaje de la aserción —esta vez
solo quedó el nombre de la prueba— y anotarlo acá. Con el mensaje se sabe si
espera un widget que no llegó a dibujarse (carga) o un dato que otro archivo
le movió (estado compartido), que son las dos ramas que hoy siguen abiertas.
