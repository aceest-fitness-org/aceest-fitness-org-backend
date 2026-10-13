# ACEest Fitness & Gym: Backend API

[![CI](https://github.com/aceest-fitness-org/aceest-fitness-org-backend/actions/workflows/main.yml/badge.svg)](https://github.com/aceest-fitness-org/aceest-fitness-org-backend/actions/workflows/main.yml)

Flask REST API for the ACEest Fitness & Gym platform. It serves the training programs (workout plan, nutrition plan, display color and calorie factor) used by the ACEest client application. The backend is **versioned**: every release lives in its own module under `app/`, and the newest one is served automatically. The service is containerized with Docker, tested with Pytest, and validated by GitHub Actions and Jenkins.

## Tech stack

Python 3.12, Flask, Gunicorn, Pytest, flake8, Docker, GitHub Actions, Jenkins.

## API endpoints (version 1.1)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check, returns `{"status": "ok", "version": "1.1"}` |
| GET | `/programs` | List all programs (`code`, `name`, `color`, `calorie_factor`) |
| GET | `/programs/<key>` | One program with its workout and diet plan. `<key>` is a code (`FL`, `MG`, `BG`) or the full name, and matching ignores case |

Unknown programs return `404` with a JSON `error` message. Later versions add endpoints; each module in `app/` documents its own at the top of the file.

## Project structure

```
.
├── .github/workflows/main.yml   # GitHub Actions pipeline
├── app/
│   ├── __init__.py
│   └── app_v1_1.py              # one module per version: app_v1_2.py, app_v2_1.py, ...
├── tests/
│   ├── test_v1_1.py             # one test file per version
│   └── test_wsgi.py             # tests for version selection
├── wsgi.py                      # entry point: serves the newest app/app_v*.py
├── Dockerfile                   # Multi-stage build (test + runtime)
├── Jenkinsfile                  # Jenkins pipeline
├── pytest.ini
└── requirements.txt
```

## How versioning works

`wsgi.py` looks at every `app/app_v*.py` file and serves the highest version, comparing numbers properly (so `app_v1_10` is newer than `app_v1_2`). To release a new version:

1. Add `app/app_v1_2.py` with a `create_app()` function.
2. Add `tests/test_v1_2.py`.
3. Push. The pipelines, the Docker image and the test run all pick up the new version without any other change.

To run a specific version instead of the newest, set `APP_MODULE` to the module name, for example `APP_MODULE=app_v1_1`.

## Local setup and execution

Requires Python 3.10 or newer (CI uses 3.12) and Git.

```bash
git clone https://github.com/aceest-fitness-org/aceest-fitness-org-backend.git
cd aceest-fitness-org-backend

python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

flask --app wsgi:create_app run --port 5000     # serves the newest version
```

To run an older version:

```bash
APP_MODULE=app_v1_1 flask --app wsgi:create_app run              # macOS / Linux / Git Bash
$env:APP_MODULE="app_v1_1"; flask --app wsgi:create_app run      # Windows PowerShell
```

Try it from a second terminal:

```bash
curl localhost:5000/health
curl localhost:5000/programs
curl localhost:5000/programs/FL
```

On macOS, port 5000 can be taken by AirPlay Receiver. If you see "Address already in use", use another port, for example `--port 5001`.

## Running the tests manually

```bash
pytest -v                                   # every version's tests, plus the wsgi tests
pytest tests/test_v1_1.py -v                # one version
flake8 --max-line-length=100 .              # lint (no output means clean)
```

The suite covers each version's endpoints (success paths, lookup by code and by full name, case-insensitive matching, unknown program returning 404) and the version selection itself. The selection tests check that the newest version wins, that numbers sort correctly, that `APP_MODULE` overrides the choice, and that every version found in `app/` loads and answers `/health`.

### Tests inside Docker

This runs the same suite in the environment that production uses:

```bash
docker build --target test -t aceest-api:test .
docker run --rm aceest-api:test                                          # Pytest
docker run --rm aceest-api:test python -m flake8 --max-line-length=100 . # lint
```

## Running with Docker

```bash
docker build -t aceest-api .
docker run -d --name aceest-api -p 5000:5000 aceest-api
curl localhost:5000/health
docker stop aceest-api
```

Pin an older version at run time with `-e APP_MODULE=app_v1_1`, or at build time with `--build-arg APP_MODULE=app_v1_1`.

The Dockerfile has these stages:

| Stage | Purpose |
|---|---|
| `base` | Slim Python image and project label |
| `deps` | Installs the dependencies, cached until `requirements.txt` changes |
| `test` | Adds the whole repository including tests, used by CI and Jenkins |
| `runtime` | Default target. Contains only `wsgi.py` and `app/`, runs Gunicorn as a non-root user, and has a built-in health check |

## CI/CD overview

Both pipelines run the same checks from the same commands, so a result that passes in one should pass in the other.

### GitHub Actions (`.github/workflows/main.yml`)

Triggered on every `push` and `pull_request`. It has two jobs, and the second runs only if the first passes.

1. **Build & Lint**: installs dependencies, compiles the code to catch syntax errors (`compileall`), and runs flake8.
2. **Docker Image & Tests**: builds the `test` image, runs Pytest inside the container, builds the production image, then starts it and checks `/health`.

A red job blocks the pull request from merging when branch protection requires these checks.

### Jenkins (`Jenkinsfile`)

A Pipeline job, configured as "Pipeline script from SCM", pulls the latest code from this repository and acts as a second, independent quality gate in a controlled build environment. It polls GitHub every 2 minutes for new commits.

| Stage | What it does |
|---|---|
| Checkout | Pulls the latest commit from GitHub |
| Clean Build | `docker build --no-cache`, rebuilding the environment from scratch |
| Lint | Runs flake8 inside the container |
| Test | Runs Pytest for every version inside the container |
| Build Release Image | Builds the production image and tags it with the Jenkins build number and `latest` |
| Smoke Test | Runs the release image, prints which version it serves, and checks that `/health` responds |

After a successful build, the pipeline deletes the temporary test image and keeps only the 3 newest release images, so old builds don't fill the disk. The Jenkinsfile works on Windows and Linux agents and needs Docker and Git available on the Jenkins machine.

## Branching and commits

- `main` holds stable code and `dev` is the integration branch.
- Work happens on short-lived branches such as `feature/*`, `fix/*` and `infra/*`. Changes reach `dev` and then `main` through pull requests, and the Actions checks must pass first.
- Commit messages follow a type prefix: `feat:`, `fix:`, `test:`, `build:`, `ci:`, `style:`, `docs:`.