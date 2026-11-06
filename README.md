# Backend (FastAPI)

API propia que funciona como **intermediario** entre el frontend y el SII del ITC
(`https://sii.celaya.tecnm.mx/api`). El frontend nunca llama al SII: todo pasa por aquí.

Además del proxy al SII, este servicio contiene la lógica y los datos del **What-If Simulator**:
- la retícula (plan de estudios) modelada como un grafo dirigido acíclico (DAG);
- la ruta crítica hacia el egreso;
- la detección de cuellos de botella;
- la simulación de escenarios.

## Tabla de contenido
- [Stack](#stack)
- [Arquitectura en 4 capas](#arquitectura-en-4-capas)
- [Base de datos](#base-de-datos)
- [Sesión y token](#sesión-y-token)
- [Endpoints](#endpoints)
- [Despliegue local](#despliegue-local)
- [Pruebas](#pruebas)
- [Variables de entorno](#variables-de-entorno)
- [Problemas comunes](#problemas-comunes)
- [Despliegue en Render](#despliegue-en-render)

---

## Stack

| Pieza | Uso |
|---|---|
| **FastAPI** + Uvicorn | API HTTP, validación y documentación OpenAPI (`/docs`) |
| **Pydantic v2** + pydantic-settings | DTOs (JSON en camelCase) y configuración desde `.env` |
| **httpx** (async) | Cliente del SII con *timeout* y reintento |
| **SQLAlchemy 2** (async) + **asyncpg** | Acceso a Supabase (PostgreSQL) |
| **Alembic** | Migraciones del esquema |
| **pytest** + respx + aiosqlite | Pruebas unitarias, de integración y de API |

## Arquitectura en 4 capas

```
app/
├── core/            Transversal: configuración, errores de dominio, logging
├── interaction/     CAPA DE INTERACCIÓN: routers, DTOs (schemas), dependencias, manejo de errores
├── application/     CAPA DE APLICACIÓN: casos de uso (services), modelos de dominio, puertos (Protocols)
│   └── whatif/engine/   Motor What-If en Python puro (grafo, proyección, ruta crítica, cuellos de botella)
├── integration/     CAPA DE INTEGRACIÓN: cliente del SII + mapeo de JSON crudo → dominio
└── data/            CAPA DE DATOS: ORM, repositorios, migraciones (Alembic) y seed de la retícula
```

**Regla de dependencias:** `interaction → application → ports ← (integration, data)`.

- Los servicios solo conocen las interfaces de `application/ports.py`.
- Las implementaciones reales (cliente SII, repositorios SQL) se inyectan con `Depends` de FastAPI.
- Gracias a esto, el motor y los servicios se prueban sin red ni base de datos.

```
Frontend ──HTTP──▶ interaction ──▶ application ──▶ ports
                                                     ├──▶ integration ──▶ SII ITC
                                                     └──▶ data ─────────▶ Supabase
```

## Base de datos

Tablas propias (Supabase / PostgreSQL):

| Tabla | Contenido |
|---|---|
| `curricula` | Plan de estudios ISIC-2010-224 con la especialidad IDP |
| `subjects` | Materias: créditos, semestre sugerido, posición en la retícula y umbral de créditos (`min_credit_pct`) |
| `requisites` | Aristas del DAG, de tipo `prereq` o `coreq` |
| `curriculum_rules` | Carga máxima y mínima por semestre, materias en verano y calificación aprobatoria |
| `students` | Número de control, nombre y último acceso |
| `sessions` | Sesiones activas: **hash SHA-256** del token y su expiración |
| `scenarios` | Escenarios What-If guardados por cada estudiante |

Notas:
- El kardex **no** se guarda. El SII es la única fuente de verdad y se consulta en vivo en cada análisis.
- La migración activa **RLS** en todas las tablas. Así, la API REST pública de Supabase no expone nada;
  solo el backend se conecta con el usuario `postgres`.

## Sesión y token

- **Login:**
  - `POST /auth/login` valida las credenciales contra el SII y consulta el perfil.
  - Registra la sesión con `expires_at = min(exp del JWT, ahora + SESSION_TTL_MINUTES)`.
- **Peticiones protegidas:**
  - Requieren `Authorization: Bearer <token>`.
  - Si el token no existe o ya expiró, responden `401` con `SESSION_EXPIRED` o `INVALID_TOKEN`.
- **Si el SII responde 401**, la sesión se borra y se responde `SESSION_EXPIRED`.
- **No hay endpoint de logout**: el frontend simplemente olvida el token.
- **Nunca se guardan ni se registran** contraseñas ni tokens en claro.

## Endpoints

Todos van bajo `/api/v1`. Todos, excepto el login, requieren el token Bearer.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/auth/login` | Inicia sesión con las credenciales del SII |
| GET | `/students/me` | Perfil del estudiante |
| GET | `/students/me/grades` | Calificaciones del periodo actual |
| GET | `/students/me/kardex` | Historial académico completo |
| GET | `/students/me/schedule` | Horario del semestre actual |
| GET | `/whatif/analysis` | Análisis base de la trayectoria |
| POST | `/whatif/simulate` | Simula un escenario sin guardarlo |
| GET · POST | `/whatif/scenarios` | Lista y crea escenarios guardados |
| GET · PUT · DELETE | `/whatif/scenarios/{id}` | Consulta (recalculado con el kardex actual), actualiza o borra un escenario |
| GET · POST · PUT · DELETE | `/admin/subjects[/{clave}]` | CRUD de materias *(solo admins)* |
| GET · POST · DELETE | `/admin/requisites[/{id}]` | Requisitos; un ciclo se rechaza con `409 CYCLE_DETECTED` *(solo admins)* |
| GET · PUT | `/admin/rules` | Reglas de carga académica *(solo admins)* |

Endpoints auxiliares, fuera de `/api/v1`:
- `GET /health`: estado del servicio.
- `GET /docs`: Swagger UI.

Todos los errores tienen la misma forma:

```json
{ "error": { "code": "SESSION_EXPIRED", "message": "…", "details": null } }
```

---

## Despliegue local

### Requisitos
- **Python 3.13**. Revisa tu versión con `python3 --version`.
- Un proyecto de **Supabase** con su cadena de conexión.

### Flujo

```
1. Crear el entorno virtual  →  2. Instalar dependencias  →  3. Configurar .env
        →  4. Migrar la BD  →  5. Cargar la retícula  →  6. Levantar la API  →  7. Verificar
```

**1. Crear y activar el entorno virtual** (desde la raíz del repositorio):

```bash
cd backend
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

En Windows: `.venv\Scripts\activate`

**2. Instalar dependencias.** Este comando incluye las de pruebas; en producción basta con
`requirements.txt`.

```bash
pip install -r requirements-dev.txt
```

**3. Configurar variables de entorno:**

```bash
cp .env.example .env
```

Edita `.env` y pega en `DATABASE_URL` tu cadena de Supabase:
- Ruta: Supabase → **Connect** → **Session pooler**.
- Pégala tal cual, con el prefijo `postgresql://`. El backend la convierte a `asyncpg` por sí solo.
- Si tu contraseña tiene caracteres especiales, codifícalos para URL (por ejemplo, `@` → `%40`).

**4. Crear las tablas** (activa RLS):

```bash
alembic upgrade head
```

**5. Cargar la retícula.** Se cargan 54 materias, 41 requisitos y las reglas de carga. Solo inserta si
la retícula aún no existe.

```bash
python -m app.data.seed.seed
```

Para reemplazar materias, requisitos y reglas con el JSON del seed, agrega `--reset`.

**6. Levantar la API:**

```bash
uvicorn app.main:app --reload --port 8000
```

**7. Verificar:**
- <http://localhost:8000/health> → `{"status":"ok"}`
- <http://localhost:8000/docs> → documentación interactiva.
- Para probar los endpoints protegidos desde `/docs`:
  1. Haz login en `POST /api/v1/auth/login`.
  2. Copia el `accessToken` de la respuesta.
  3. Pulsa **Authorize** y pégalo.

> Para que el frontend local pueda llamar a la API, `CORS_ORIGINS` debe incluir
> `http://localhost:5173` (ya viene así en `.env.example`).

## Pruebas

```bash
pytest
```

- **48 pruebas** en tres grupos:
  - `unit/`: el motor What-If;
  - `integration/`: el cliente del SII simulado con `respx`;
  - `api/`: la API de punta a punta con SQLite en memoria y un SII falso.
- No necesitan red ni Supabase.

> Los *fixtures* en `tests/fixtures/` provienen de respuestas reales del SII. Anonimízalos antes de
> publicar el repositorio.

## Variables de entorno

| Variable | Ejemplo | Descripción |
|---|---|---|
| `SII_BASE_URL` | `https://sii.celaya.tecnm.mx/api` | URL base del SII |
| `SII_TIMEOUT_SECONDS` | `10` | *Timeout* de cada llamada al SII |
| `DATABASE_URL` | `postgresql://postgres.<ref>:<pwd>@aws-0-<región>.pooler.supabase.com:5432/postgres` | Conexión a Supabase |
| `SESSION_TTL_MINUTES` | `30` | Duración de la sesión. Nunca supera el `exp` del token del SII |
| `CORS_ORIGINS` | `http://localhost:5173` | Orígenes permitidos, separados por comas |
| `ADMIN_CONTROL_NUMBERS` | `23031035` | Números de control con acceso a `/admin`, separados por comas |

## Problemas comunes

| Síntoma | Causa y solución |
|---|---|
| `OSError: [Errno 101] Network is unreachable` al migrar | Estás usando el host directo `db.<ref>.supabase.co`, que solo tiene IPv6. Usa la cadena **Session pooler**. |
| `password authentication failed` | La contraseña es incorrecta, o el usuario no es `postgres.<ref>` en el pooler. |
| `Tenant or user not found` | La región del host del pooler no corresponde a tu proyecto. Cópiala tal cual del panel **Connect**. |
| El navegador muestra un error de CORS | Falta el origen del frontend en `CORS_ORIGINS`. Va sin `/` final. |
| `503 SII_UNAVAILABLE` | El SII no respondió a tiempo o está caído. |

## Despliegue en Render

El archivo [`render.yaml`](../render.yaml) en la raíz describe el servicio. La configuración es:

- **Root Directory:** `backend`
- **Build:** `pip install -r requirements.txt`
- **Start:** `alembic upgrade head && python -m app.data.seed.seed && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Health check:** `/health`
- **Variables:**
  - las de la tabla anterior, más `PYTHON_VERSION=3.13.5`;
  - `CORS_ORIGINS` debe ser la URL de Vercel;
  - `DATABASE_URL` debe ser la del **Session pooler**.
