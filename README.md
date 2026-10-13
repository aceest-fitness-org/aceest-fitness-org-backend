# ACEest Fitness & Gym: Backend API

[![CI](https://github.com/aceest-fitness-org/aceest-fitness-org-backend/actions/workflows/main.yml/badge.svg)](https://github.com/aceest-fitness-org/aceest-fitness-org-backend/actions/workflows/main.yml)

Flask REST API for the ACEest Fitness & Gym platform. It serves the training programs (workout plan, nutrition plan and display color) and the site metrics used by the ACEest client application. The service is containerized with Docker, tested with Pytest, and validated automatically by GitHub Actions and Jenkins.

## Tech stack

Python 3.12, Flask, Gunicorn, Pytest, flake8, Docker, GitHub Actions, Jenkins.

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check, returns `{"status": "ok"}` |
| GET | `/programs` | List all programs (`code`, `name`, `color`) |
| GET | `/programs/<key>` | One program with its workout and diet plan. `<key>` is a code (`FL`, `MG`, `BG`) or the full name, and matching ignores case |
| GET | `/metrics` | Site capacity, area and break-even figures |

Unknown programs return `404` with a JSON `error` message.

## Project structure

```
.
├── .github/workflows/main.yml   # GitHub Actions pipeline
├── tests/test_app.py            # Pytest suite
├── app.py                       # Flask application
├── Dockerfile                   # Multi-stage build (test + runtime)
├── Jenkinsfile                  # Jenkins pipeline
├── pytest.ini
└── requirements.txt
```

## Local setup and execution

Requires Python 3.10 or newer and Git.

```bash
git clone https://github.com/aceest-fitness-org/aceest-fitness-org-backend.git
cd aceest-fitness-org-backend

python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

python app.py                       # starts on http://localhost:5000
```

Try it from a second terminal:

```bash
curl localhost:5000/health
curl localhost:5000/programs
curl localhost:5000/programs/FL
```

On macOS, port 5000 can be taken by AirPlay Receiver. If you see "Address already in use", turn that feature off or change the port in `app.py`.

## Running the tests manually

```bash
pytest -v                                   # run the full suite
flake8 --max-line-length=100 .              # lint (no output means clean)
```

The suite covers every endpoint plus the lookup logic: success paths, lookup by code and by full name, case-insensitive matching, unknown program (404), and the health and metrics responses.

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

The Dockerfile has three stages:

| Stage | Purpose |
|---|---|
| `base` | Slim Python image plus dependencies, cached until `requirements.txt` changes |
| `test` | Adds the test suite, used by CI and Jenkins |
| `runtime` | Default target. Runs Gunicorn as a non-root user and has a built-in health check |

## CI/CD overview

Both pipelines run the same checks from the same commands, so a result that passes in one should pass in the other.

### GitHub Actions (`.github/workflows/main.yml`)

Triggered on every `push` and `pull_request`. It has two jobs, and the second runs only if the first passes.

1. **Build & Lint**: installs dependencies, compiles the code to catch syntax errors (`compileall`), and runs flake8.
2. **Docker Image & Tests**: builds the `test` image, runs Pytest inside the container, builds the production image, then starts it and checks `/health`.

A red job blocks the pull request from merging when branch protection requires these checks.

### Jenkins (`Jenkinsfile`)

A Pipeline job, configured as "Pipeline script from SCM", pulls the latest code from this repository and acts as a second, independent quality gate in a controlled build environment. It polls GitHub every 5 minutes for new commits.

| Stage | What it does |
|---|---|
| Checkout | Pulls the latest commit from GitHub |
| Clean Build | `docker build --no-cache`, rebuilding the environment from scratch |
| Lint | Runs flake8 inside the container |
| Test | Runs Pytest inside the container |
| Build Release Image | Builds the production image and tags it with the Jenkins build number and `latest` |
| Smoke Test | Runs the release image and checks that `/health` responds |

The Jenkinsfile works on Windows and Linux agents. It needs Docker and Git available on the Jenkins machine.

## Branching and commits

- `main` holds stable code and `dev` is the integration branch.
- Work happens on short-lived branches such as `feature/*`, `fix/*` and `infra/*`. Changes reach `dev` and then `main` through pull requests, and the Actions checks must pass first.
- Commit messages follow a type prefix: `feat:`, `fix:`, `test:`, `build:`, `ci:`, `style:`, `docs:`.