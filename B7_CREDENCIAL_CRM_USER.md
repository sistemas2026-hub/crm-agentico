# B-7 — CREDENCIAL DE `crm_user`

Fecha: 2026-09-19 · **PASS**

```
CREDENCIAL_CRM_USER    = ESTABLECIDA
AUTENTICACION_CRM_USER = PASS
PERMISOS_POST_CAMBIO   = SIN_CAMBIOS
```

La contraseña no aparece en este informe, ni en la consola, ni en ningún archivo
del repositorio, ni en git. Sin commit, sin `git stash`.

---

## La decisión que cambió cómo se hizo

Antes de ejecutar nada medí el cifrado del tramo, y el resultado obligó a hacerlo
distinto de lo previsto:

```
cifrado del tramo cliente -> pooler : False   (libpq: ssl_in_use)
password_encryption del servidor    : scram-sha-256
```

**La conexión no va cifrada.** Mandar `ALTER ROLE crm_user WITH PASSWORD '<texto
plano>'` habría puesto una credencial nueva **en claro sobre la red**.

PostgreSQL acepta un **verificador SCRAM-SHA-256 ya calculado** en lugar del
texto plano, y lo guarda tal cual — es exactamente lo que el servidor computaría
por su cuenta. Calculándolo en esta máquina, **la contraseña nunca sale de
aquí**: por la red viaja un hash del que no se puede volver atrás.

```
SaltedPassword = PBKDF2-HMAC-SHA256(password, salt, 4096, 32)
ClientKey      = HMAC(SaltedPassword, "Client Key")
StoredKey      = SHA256(ClientKey)
ServerKey      = HMAC(SaltedPassword, "Server Key")
verificador    = SCRAM-SHA-256$4096:b64(salt)$b64(StoredKey):b64(ServerKey)
```

La contraseña se generó con `secrets` sobre un alfabeto ASCII (`A-Za-z0-9`, 40
caracteres), así que la normalización SASLprep es la identidad y no hace falta
implementarla — un detalle que, mal resuelto, produce una credencial que se
guarda pero no autentica.

### Ensayado antes de producción

En `pg-b7`, como con cada escritura productiva de este proyecto:

```
password_encryption           : scram-sha-256
ALTER ROLE con verificador    : ejecutado
guardado como SCRAM-SHA-256   : True
AUTENTICA                     : ('crm_user', 'crm_user')
contraseña del aislado restaurada a la descartable
```

Si el cálculo hubiera estado mal, el `ALTER ROLE` habría pasado igual y la
autenticación habría fallado después. Por eso se probó antes.

---

## 1. Identidad que ejecutó

```
current_user = postgres   session_user = postgres
```

El script **aborta** si la identidad es `crm_user` (nadie cambia su propia
contraseña) o si no es la administrativa esperada. No se modificó ningún otro
rol.

## 2. La sentencia

```sql
ALTER ROLE "crm_user" WITH PASSWORD '<verificador SCRAM-SHA-256>';
```

Construida con `psycopg.sql.Identifier` y `Literal` — no por concatenación de
cadenas.

## 3. Privilegios: **los 22 campos, idénticos**

Se registró el estado antes y después y se comparó campo por campo, leyendo el
«después» con una **conexión independiente** de la que escribió:

| | ANTES | DESPUÉS |
|---|---|---|
| `crm_user` CREATE / USAGE en public | False / True | False / True |
| tablas SELECT/INSERT/UPDATE/DELETE | 135/135/135/135 | 135/135/135/135 |
| tablas TRUNCATE | 0 | 0 |
| secuencias USAGE/SELECT/UPDATE | 51/51/0 | 51/51/0 |
| EXECUTE en funciones de public | 149 | 149 |
| `crm_user` bypassrls / super / createdb / createrole / login | F/F/F/F/T | F/F/F/F/T |
| `crm_user` TEMPORARY | True | True |
| `crm_migrator` CREATE / USAGE / bypassrls / super | T/T/F/F | T/T/F/F |
| total de roles | 41 | 41 |

```
los 22 campos, IDENTICOS
CREATE sobre public sigue revocado : True
bypassrls sigue desactivado        : True
crm_migrator intacto               : True
```

## 4. Autenticación y capacidades, con la credencial nueva

Conexión aislada a través del pooler, con el sufijo de Supavisor:

```
autenticacion      : True
identidad          : ('crm_user', 'crm_user')
SELECT             : 2 organizaciones leidas
INSERT             : True
UPDATE             : True
DELETE             : True
CREATE bloqueado   : True
setval bloqueado   : True
pg_temp            : True
bypassrls          : False
```

**El `INSERT`/`UPDATE`/`DELETE` no tocó ningún dato de negocio.** Se hicieron
dentro de una transacción con `ROLLBACK`: se prueba el permiso, no se persiste
nada. Verificado después con una conexión independiente:

```
filas de prueba en activity : 0
tablas 'b7_*' en public     : 0
tablas en public            : 135
```

## 5. Dónde quedó la contraseña

```
C:\Users\Usuario\b8_crm_user_clave.txt   (1 linea, 40 caracteres)
```

Fuera del repositorio, junto a `b8_crm_migrator_clave.txt` — el mismo patrón que
el proyecto ya usa para este tipo de archivo.

Comprobado, no supuesto:

```
archivos del repositorio que contienen la credencial : 0
apariciones en el historial de git                   : ninguna
```

> Una comprobación mía marcó «5 archivos sospechosos» en `git status`. Los miré
> uno por uno antes de alarmar: son código cuyo **nombre** contiene
> «credenciales» (`common/credenciales.py`, `verificar_credenciales.py` y sus
> tres pruebas), todos previos a este bloque. Ninguno contiene la credencial.

---

## Cómo introducirla en Dokploy sin exponerla

No existe un canal automatizado: **no tengo acceso a Dokploy**, así que el
traslado es manual. Sin pegarla en un chat, un ticket ni un commit:

1. Abrir `C:\Users\Usuario\b8_crm_user_clave.txt` y copiar la línea.
2. Dokploy → proyecto de la plataforma (**`crm-agentico-*`**, no el de Supabase)
   → variables del servicio Compose → `DBPASSWORD`.
3. En la misma edición, `DBUSER = crm_user.<el mismo sufijo de pooler que ya
   usa el valor actual>`.
4. **Redeploy / Recreate**, no *Save*.
5. Conservar el archivo mientras B-7 siga abierto; es la única copia. Cuando el
   cambio esté verificado y la credencial guardada en el gestor de secretos del
   equipo, borrarlo.

Si al guardar sale **`UNAUTHORIZED` en rojo**, la sesión de Dokploy caducó y el
cambio **no se guardó**: recargar, entrar de nuevo y repetir.

---

## `[HALLAZGO]` El tramo a la base no va cifrado

`ssl_in_use = False` en la conexión de este equipo al pooler. No lo introduje yo
y no lo cambié: es el estado actual, y significa que **la contraseña de
`postgres` viaja en claro en cada conexión** que hace esta máquina — y,
según cómo esté desplegado, posiblemente también las del CRM y el motor si salen
de la red interna del VPS.

Para esta credencial lo esquivé con el verificador SCRAM. **No lo arregla**: el
resto de las conexiones siguen igual. Queda reportado, fuera del alcance de este
bloque.

---

## Estado de producción al cerrar

```
DBUSER efectivo      postgres   ok   <- sin cambiar, como pide el bloque
tablas en public     135        ok
roles                41         ok
kill switch          detenido   ok
FORCE RLS            66         ok
GUC jwt_secret       presente (sin tocar)
AUTONOMIA_2_ACTIVA   ausente = apagada
```

La única escritura de producción fue el `ALTER ROLE` autorizado. Todo lo demás
se consultó con `transaction_read_only = on` verificado en el servidor.

---

## CRITERIO DE SALIDA

| # | Criterio | Resultado |
|---|---|---|
| 1 | `crm_user` tiene contraseña nueva | **PASS** |
| 2 | no quedó en repo/log/informe | **PASS** — 0 archivos, 0 commits |
| 3 | `crm_user` puede autenticarse | **PASS** |
| 4 | privilegios exactamente iguales | **PASS** — 22/22 campos |
| 5 | `CREATE` sigue revocado | **PASS** |
| 6 | `BYPASSRLS` sigue desactivado | **PASS** |
| 7 | `crm_migrator` sin modificar | **PASS** |
| 8 | ningún otro componente modificado | **PASS** |

### **PASS**

B-7 sigue siendo **PARCIAL**. Esto desbloquea el cambio de `DBUSER`, que sigue
pendiente de Dokploy, y no cambia nada sobre el camino indirecto de
`service_role`, que continúa abierto por la decisión documentada en
`B7_DECISION_NO_ROTAR.md`.

---

**No se cambió `DBUSER`. No se hizo redeploy. No se activó Autonomía 2. No se
levantó el kill switch. No se ejecutó `crear_tag_crm`. No se hizo commit.**
