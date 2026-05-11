# Bazaar — Microservice Template

Base inicial para el microservicio `user-service`, construido sobre el template de microservicios con FastAPI y PostgreSQL.

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.11+, FastAPI, Pydantic, SQLAlchemy |
| Base de datos | PostgreSQL (configurable por env vars) |
| Contenedor | Docker (multi-stage, non-root) |
| Orquestación | Kubernetes (DigitalOcean) |
| CI/CD | GitHub Actions → GHCR → DOKS |

## Estructura del proyecto

```
├── src/
│   ├── api/            # Routers de FastAPI
│   │   └── health.py   # /livez y /readyz
│   ├── core/           # Configuración, DB, logging
│   │   ├── config.py
│   │   ├── database.py  # Engine, sesión, base, y retry de conexión
│   │   ├── dependencies.py
│   │   └── logging.py
│   ├── models/         # Entidades SQLAlchemy (vacío — extender aquí)
│   ├── schemas/        # Modelos Pydantic (vacío — extender aquí)
│   ├── services/       # Lógica de negocio (vacío — extender aquí)
│   └── main.py         # Punto de entrada
├── tests/
│   ├── conftest.py
│   └── test_health.py
├── scripts/
│   ├── run_tests.sh    # Wrapper para correr tests (Linux/macOS)
│   └── run_tests.ps1   # Wrapper para correr tests (Windows)
├── k8s/
│   ├── app-deployment.yaml   # Deployment del microservicio
│   ├── app-service.yaml      # Service (ClusterIP) del microservicio
│   ├── db-deployment.yaml    # Deployment de PostgreSQL
│   ├── db-service.yaml       # Service (ClusterIP) de PostgreSQL
│   ├── db-pvc.yaml           # PersistentVolumeClaim para la BD
│   └── secret.yaml           # ⚠️ Template — NO commitear valores reales
├── .github/workflows/
│   └── deploy.yml
├── Dockerfile              # Imagen de producción
├── Dockerfile.test         # Imagen para correr tests
├── docker-compose.test.yml # Levanta PostgreSQL + test runner
├── requirements.txt
└── .env.example
```

## Endpoints
Tambien tener en cuenta que fastapi genera documentacion de endpoints estylo swaggerui en el endpoint `/docs`

### Health

#### GET /livez

Liveness probe. Verifica que el proceso HTTP está vivo.

- `200 OK`

```json
{
	"status": "alive"
}
```

- Errores:
	- No tiene errores de negocio implementados.

#### GET /readyz

Readiness probe. Verifica conectividad con la base de datos.

- `200 OK`

```json
{
	"status": "ready"
}
```

- `503 Service Unavailable` (cuando la base no es alcanzable)

```json
{
	"status": "unavailable"
}
```

### Auth

#### POST /auth/register

Registra un usuario nuevo.

Body esperado:

```json
{
	"email": "user@example.com",
	"password": "Correct-P4ssw0rd!",
	"name": "Test User"
}
```

- `201 Created`

```json
{
	"id": 1,
	"email": "user@example.com",
	"name": "Test User",
	"is_active": true,
	"created_at": "2026-04-15T12:34:56.789012"
}
```

- Errores:
	- `400 Bad Request` si el email ya existe.

```json
{
	"detail": "User with this email already exists"
}
```

	- `422 Unprocessable Entity` si el payload es inválido (ej: email inválido o password que no cumple reglas).

Ejemplo de error de validación:

```json
{
	"detail": [
		{
			"type": "value_error",
			"loc": ["body", "password"],
			"msg": "Value error, Password must contain at least one special character",
			"input": "NoSpecialChars12"
		}
	]
}
```

#### POST /auth/login

Autentica un usuario y devuelve JWT.

Body esperado:

```json
{
	"email": "user@example.com",
	"password": "Correct-P4ssw0rd!"
}
```

- `200 OK`

```json
{
	"access_token": "<jwt>",
	"token_type": "bearer",
}
```

- Errores:
	- `401 Unauthorized` si el email no existe o la contraseña es incorrecta.

```json
{
	"detail": "Invalid credentials"
}
```

	- `422 Unprocessable Entity` si el payload es inválido (ej: email mal formado o campos faltantes).

## Mapeo de Rutas
Las rutas del microservicio se mapean al ambiente de kubernetes con pequeñas diferencias:
* `/auth/login` -> `/login`
* `/auth/register` -> `/register`
* `/livez` -> `/livez`
* `/readyz` -> `/readyz`

Esto se configura en el [ingress controller config](k8s/ingress.yaml) de este microservicio 

## Setup local

```bash
# 1. Clonar y entrar al directorio
git clone https://github.com/bazaar-grupo16/user-microservice.git && cd user-microservice

# 2. Crear entorno virtual
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con las credenciales de tu base de datos local

# 5. Levantar la aplicación
uvicorn src.main:app --reload
```

## Conectarse al cluster de DigitalOcean

Requisitos:
- Tener instalado [doctl](https://docs.digitalocean.com/reference/doctl/)
- Tener instalado [kubectl](https://kubernetes.io/docs/tasks/tools/)

```bash
# 1. Iniciar sesión en doctl
doctl auth init --context <NAME>
doctl auth switch --context <NAME>

# 2. Obtener credenciales del cluster
doctl kubernetes cluster kubeconfig save <CLUSTER_ID>
```

## Endpoints disponibles

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/livez` | Liveness probe — siempre 200 |
| GET | `/readyz` | Readiness probe — verifica conexión a DB |
| POST | `/auth/register` | Registro de usuario |
| POST | `/auth/login` | Login y emisión de token JWT |
| GET | `/docs` | Swagger UI (auto-generado) |
| GET | `/redoc` | ReDoc (auto-generado) |

## Tests

Los tests corren contra una **base de datos PostgreSQL real** usando Docker Compose. No se usa mocking.

El archivo `docker-compose.test.yml` levanta:
1. Un contenedor **PostgreSQL 16** como base de datos.
2. Un contenedor **test-runner** que ejecuta `pytest` contra esa base de datos.

### Correr los tests

```bash
# Linux / macOS
./scripts/run_tests.sh

# Windows (PowerShell)
.\scripts\run_tests.ps1

# O directamente con docker compose
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

> Los contenedores se limpian automáticamente al finalizar.

## Docker

```bash
docker build -t user-service .
docker run -p 8000:8000 --env-file .env user-service
```

## Kubernetes

Los manifiestos en `k8s/` despliegan el microservicio junto con su propia base de datos PostgreSQL dentro del cluster.

### Variables de entorno requeridas (GitHub Secrets)

| Secret | Descripción |
|--------|-------------|
| `DIGITALOCEAN_ACCESS_TOKEN` | Personal Access Token de DigitalOcean |
| `DB_USER` | Usuario de la base de datos |
| `DB_PASSWORD` | Contraseña de la base de datos |
| `DB_NAME` | Nombre de la base de datos |

`DB_HOST` y `DB_PORT` están fijos en `k8s/secret.yaml` (`bazaar-db:5432`) ya que la BD corre dentro del cluster.
Si se utilizase una base de datos externa, se deberían agregar las variables de entorno correspondientes.

### Deploy manual

```bash
# Crear el namespace (solo la primera vez)
kubectl create namespace bazaar-dev

# Aplicar todos los manifiestos en orden
kubectl apply -f k8s/db-pvc.yaml       -n bazaar-dev
kubectl apply -f k8s/db-deployment.yaml -n bazaar-dev
kubectl apply -f k8s/db-service.yaml    -n bazaar-dev
kubectl apply -f k8s/secret.yaml        -n bazaar-dev
kubectl apply -f k8s/app-deployment.yaml -n bazaar-dev
kubectl apply -f k8s/app-service.yaml   -n bazaar-dev
```

### CI/CD automático

El pipeline en `.github/workflows/deploy.yml` corre automáticamente en cada push a `main`:

| Job | Se ejecuta cuando cambia... |
|-----|----------------------------|
| `lint` | `src/`, `tests/`, archivos de build |
| `test` | `src/`, `tests/`, archivos de build |
| `build` | `src/`, `tests/`, archivos de build (solo push a main) |
| `deploy` | `src/` **o** `k8s/` (solo push a main) |

## Conexión a la base de datos

Al iniciar, la aplicación espera a que la base de datos esté disponible usando **backoff exponencial** (1s → 2s → 4s → … hasta 30s por intento, máximo 5 minutos en total) antes de ejecutar las migraciones y aceptar tráfico. Esto evita crasheos durante el arranque del pod cuando la BD aún está inicializándose.

## Extender el template

Para agregar una nueva entidad al microservicio:

1. Crear el modelo SQLAlchemy en `src/models/`.
2. Crear los schemas Pydantic en `src/schemas/`.
3. Implementar la lógica de negocio en `src/services/`.
4. Crear el router en `src/api/` e incluirlo en `src/main.py`.
5. Agregar tests en `tests/`.
