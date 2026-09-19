# DEXTER — ESTADO ACTUAL

Autoridad del estado. Quien empieza una sesión lee ESTO, no el historial.
Actualizar al cerrar cada gate. Si contradice a una conversación, gana este archivo.

Última actualización: 19/09/2026

---

## BASE CANÓNICA

```
HEAD        (ver git log; backend T6 en 04d835e, sobre d0d6be9)
rama        feature/bandeja-relevo
worktree    C:\tmp\dexter-bandeja
```

Nada pusheado. El backend T6 **sí** está commiteado; la UI de T6 sigue en el
árbol de trabajo, sin commitear.

## WORKTREE SUCIO — resuelto en su mayor parte

El backend de esas 406 líneas quedó reparado, probado y commiteado en `04d835e`.
Lo que sigue sin commitear es la **UI de T6** (4 archivos de frontend), el cambio
de `SPEC/CONTRATO_RELEVO_IA_HUMANO.md` sobre G9, y esta documentación operativa.

Origen del draft, para la historia:

```
VERIFICADO
- modificados en una ventana de 3 min 24 s (19/09/2026, 11:27:50-11:31:14)
- orden coherente con una implementación bottom-up
- los símbolos no aparecen en ninguna rama ni worktree inspeccionado
- contenían 3 cierres de string rotos idénticos (reparados en 1.4C.0-D1b)

INFERIDO
- probablemente una única sesión de agente interrumpida
```

Sigue valiendo: **no hacer `git commit -a` aquí**, y no revertir en bloque.

## CERRADO

```
Fase 0 (componentización)   ✅
D29 (recursos del composer) ✅
D30 (origen/autor en hilo)  ✅
G9 (recibo punta a punta)   ✅ verde en producción 16/09/2026
Fase 1.1-1.4B (visual)      ✅
Contrato T6/T7              ✅ entendido y congelado
1.4C backend T6             ✅ commit 04d835e, medido contra PostgreSQL 16.14
```

## ABIERTO

```
1.4C UI                 ⏭ SIGUIENTE. El draft visual ya existe, sin commitear.
G6 sobre messages       🔒 gate de DESPLIEGUE: la migración no se midió sobre
                           una tabla poblada. NO bloquea el commit funcional.
hot path ③a/③c          ⏸ retirado y preservado, gate propio
T7 endpoint             ⏸ fuera de T6, capacidad manual futura
Fases 1.5-1.9           ⏸
smoke visual Fase 1     ⏸ QA multi-viewport diferida
```

**Fase 1.4C NO está completa**: falta la UI.

### El draft T6 se separa en cuatro asuntos, no uno

```
① T6 puro          transiciones.py entero + api.py:4370,4529-4646 + 3 piezas de UI
② contrato entrega db.py entero + _rechazo_es_definitivo + _contrato_entrega
                   + whatsapp_salidas + migración + tickets/*
③a automáticas     _atendio_baja_o_alta, _procesar_mensaje_whatsapp    → SEPARAR
③b webhook         whatsapp_webhook (statuses sin rol)                 → PERMANECE (G9)
③c avisos          whatsapp_avisar                                     → SEPARAR
```

## SIGUIENTE GATE

```
1.4C UI   el botón «Responder y devolver a IA» y sus estados
```

Entrada: `SPEC/FASE_1_CHECKPOINT.md` (sección 1.4C) y `auditorias/1.4C-D3.md`.
Lo que la UI puede dar por cierto y lo que NO debe hacer está en el checkpoint.

## BLOQUEANTES — estado tras 1.4C.0-D2

```
B2   RESUELTO. El reintento desempata por whatsapp_salidas (_salida_previa) y
     deja evidencia con el resultado honesto. Cubierto por test_t6_devolucion.
KEY  RESUELTO por separación: las tres claves con None salieron con ③a/③c.
AVI  DIFERIDO con ③c, preservado en auditorias/1.4C-hotpath-diferido.md
GUA  VERDE. usan_mecanismo vuelve a 3 sin tocar el test.
```

## ABIERTO PARA EL AUDITOR

```
1  ninguna prueba corrió contra PostgreSQL real: B1-B4 usan dobles
2  la migración sigue sin aplicar, sin ledger y con DDL no concurrente
3  el docstring de _entregar_y_registrar sigue diciendo "respuesta humana"
   — es correcto otra vez tras la separación, pero conviene releerlo
4  T7 sigue sin endpoint propio (decisión: fuera del gate B1/B2)
```
