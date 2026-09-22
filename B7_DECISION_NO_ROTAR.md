# B-7 — DECISIÓN: NO ROTAR EL SECRETO JWT

Fecha: 2026-09-19

## La decisión

**El responsable del proyecto decidió no rotar `JWT_SECRET`.** No declaró motivo,
y no se le atribuye ninguno.

Esta decisión **reemplaza** lo que dicen los informes anteriores, donde B-7
figuraba como «bloqueado por la rotación, pendiente de acceso a Dokploy». Ya no
está pendiente: está **descartado por decisión**.

## Qué queda abierto, en concreto

El camino indirecto sigue vigente. Medido, no supuesto:

```
app.settings.jwt_secret   existe en la base, legible por crm_user
service_role              bypassrls = True
authenticator             puede SET ROLE service_role
alcance de service_role   DML sobre 129 de 135 tablas de public
```

Con un `SELECT` sobre `pg_db_role_setting` y un HMAC, cualquier rol con LOGIN
puede firmar un token `service_role` válido y escribir en 129 tablas
**saltándose RLS**. Los tokens vigentes vencen en **2030-01-01**.

Agravante: **ese secreto quedó expuesto en la transcripción de la sesión de
auditoría** — al volcar `pg_db_role_setting` completo, su valor salió impreso.
Fue un error mío, reportado cuando ocurrió. Un secreto que apareció en una
transcripción debe considerarse comprometido.

## Consecuencia para B-7

**B-7 no puede declararse cerrado.** El objetivo del bloque es que el runtime
del CRM deje de tener `BYPASSRLS`; mientras este camino exista, ese privilegio
es recuperable por otra puerta.

Lo que **sí** sigue valiendo, y no depende de la rotación:

- los cuatro `REVOKE` ya aplicados sobre `crm_user` (TRUNCATE, REFERENCES,
  TRIGGER, UPDATE de secuencias);
- `REVOKE CREATE ON SCHEMA public FROM crm_user`, demostrado innecesario y
  preparado;
- el cambio de `DBUSER` a `crm_user`, con su smoke de 18 ítems verde;
- la separación de migraciones con `crm_migrator`.

Todo eso **reduce** la superficie. Lo que no hace es cerrarla: si se ejecuta,
hay que decir que B-7 quedó **parcial**, no cerrado. Llamarlo cerrado sería
falso.

## Efecto sobre Autonomía 2

`nucleo/seguridad/autonomia2.py` comprueba este prerequisito **midiéndolo contra
la base**, no con una bandera. Mientras el GUC exista, la respuesta a cualquier
intento de ejecución autónoma productiva es:

```
B7_REQUERIDO
```

aunque se encienda `AUTONOMIA_2_ACTIVA` y se levante el kill switch. **Autonomía
2 queda bloqueada por diseño**, y eso no es un efecto lateral: es lo que el
bloque de Autonomía 2 pidió explícitamente.

Si en algún momento se quiere activar Autonomía 2 sin rotar, hay que decidir
antes una de dos cosas, y ninguna es mía:

1. cerrar el camino de otra forma (retirar el GUC, quitarle `BYPASSRLS` a
   `service_role`, o revocar la lectura de `pg_db_role_setting`), o
2. cambiar deliberadamente el prerequisito de `autonomia2.py`, asumiendo por
   escrito que se activa autonomía con ese camino abierto.

## Qué se hizo al cerrar esta decisión

- Se quitaron `JWT_SECRET`, `ANON_KEY` y `SERVICE_ROLE_KEY` del `.env` del
  repositorio. **Cero referencias en código**: no las lee nadie. Siguen donde
  corresponde, en Supabase/Dokploy.
- Se borró `C:\Users\Usuario\rotacion_jwt_2026-09-19.txt`, con los secretos que
  se habían generado y que ya no se van a usar.
- Se conservan `rotar_jwt_supabase.py` y `verificar_rotacion_jwt.py` (fuera del
  repositorio). **No contienen secretos**: los calculan. Quedan disponibles si
  la decisión se revisa.

## Producción, sin cambios

```
GUC app.settings.jwt_secret : presente (sin tocar)
kill switch                 : detenido
AUTONOMIA_2_ACTIVA          : apagada
DBUSER efectivo             : postgres
tablas en public            : 135
tablas de Autonomia 2       : ausentes
crm_user CREATE en public   : True (sin revocar)
```

---

**No se rotó. No se tocó producción. No se hizo commit.**
