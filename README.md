# ACEest Fitness & Gym: Flask API (versioned)

One Flask backend per version of the original Tkinter prototype. Each version has its own module in `backend/`, its own Pytest file in `tests/`, and a matching web page in `aceest-frontend/`.

```
aceest-api/
├── app.py                 # entry point: serves any version (default: newest)
├── backend/
│   ├── app_v1_1.py ... app_v3_2_4.py
├── tests/
│   ├── test_v1_1.py ... test_v3_2_4.py
│   └── test_entrypoint.py
├── pytest.ini
└── requirements.txt
```

## Version map

| Backend module | Frontend page | Tests | Adds |
|---|---|---|---|
| `app_v1_1.py` | `v1.1.html` | 11 | Program catalogue with workout and diet plans |
| `app_v1_1_2.py` | `v1.1.2.html` | 11 | Compact plans for the client-table UI |
| `app_v2_0_1.py` | `v2.0.1.html` | 41 | SQLite clients, calorie targets, weekly progress |
| `app_v2_1_2.py` | `v2.1.2.html` | 41 | Same as 2.0.1 |
| `app_v2_2_1.py` | `v2.2.1.html` | 44 | Progress history for the adherence chart |
| `app_v2_2_4.py` | `v2.2.4.html` | 82 | Goals, workouts and exercises, body metrics, BMI |
| `app_v3_0_1.py` | `v3.0.1.html` | 82 | Same as 2.2.4 |
| `app_v3_1_2.py` | `v3.1.2.html` | 84 | Login, membership expiry, AI program generator, PDF report |
| `app_v3_2_4.py` | `v3.2.4.html` | 66 | Role-based login, membership status, workouts, PDF report |

## Run locally

```bash
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py                                        # newest version on :5000
ACEEST_VERSION=2_2_4 python app.py                   # any other version
curl localhost:5000/health                           # {"status": "ok", "version": "3.2.4"}
```

The database path comes from `DB_PATH` (default `aceest_fitness.db`). Set `ADMIN_PASSWORD` to change the seeded `admin` password (default `admin`, for development only) and `CORS_ORIGIN` to restrict the allowed browser origin (default `*`). Serve the frontend pages with `python -m http.server 8000` from `aceest-frontend/`.

## Run the tests

```bash
pytest -v                          # everything (about 470 tests, 20 s)
pytest tests/test_v3_1_2.py -v     # one version
flake8 --max-line-length=100 .     # lint, as run in CI
```

The same commands work inside Docker (`docker run --rm <image> pytest -v`) and in the GitHub Actions and Jenkins pipelines.

## What the tests cover

- **Pure logic:** calorie formula per program, input validation (`to_number`, `parse_date`), week labels, BMI categories and boundaries, AI program shape, focus and reproducibility with a seeded RNG, membership expiry, PDF structure and xref offsets.
- **Endpoints:** status codes and payloads for success paths, validation failures (400), unknown clients (404), update-versus-create behaviour, and ordering rules (progress by insertion, metrics by date, workouts newest first).
- **Security:** hashed passwords, rejected logins, SQL-injection input stored literally, sanitised PDF filenames.

## Notes on behaviour versus the desktop app

- Passwords are hashed (the Tkinter app stored plain text), and login returns the role only. There are no sessions or tokens yet, so do not expose this publicly as is.
- `POST /clients` is an upsert that keeps unspecified fields, instead of `INSERT OR REPLACE`, which wiped them.
- The PDF report is generated without third-party libraries, so the Docker image stays small.
