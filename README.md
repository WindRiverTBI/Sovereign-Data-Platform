# Sovereign-Data-Platform
Open source software platform for the Wind River Tribal Buffalo Initiative's sovereign science data

Buffalo intake, condition-report, and sampling records for the Wind River
Tribal Buffalo Initiative.

**Stack:** Python 3.14 · Django 6.1 · PostgreSQL 18 + PostGIS (GeoDjango) ·
server-rendered templates with [htmx](https://htmx.org) and
[Alpine.js](https://alpinejs.dev) · [django-shadcn](https://shadcn-django.com/)
components on Tailwind CSS 4 · uv, ruff, ty, prek, pytest.

## Running locally

Everything runs in Docker, since GeoDjango needs GDAL in the runtime:

```sh
docker compose up --build
docker compose exec web python manage.py seed_dev --superuser   # demo data
```

- App: <http://localhost:8000>. The `seed_dev` users all have the password
  `buffalo-dev`: `admin` (superuser), `shoshone-editor`, `shoshone-reader`,
  `arapahoe-editor`.
- Admin: <http://localhost:8000/admin/>
- Mailpit (captures password-reset emails): <http://localhost:8025>

The database lives in the `pgdata` volume and uploads in the `media` volume, so
both survive `docker compose down`. To start over, run `docker compose down -v`.
The first start downloads the Tailwind CLI (~110 MB) into the `tailwind` volume.

Common commands:

```sh
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py createsuperuser
docker compose run --rm web pytest
```

## Tooling (on the host)

```sh
uv sync                  # install dependencies into .venv
uv run prek install      # git hook: ruff, ty, uv-lock, whitespace/JSON/YAML/TOML checks
uv run prek run -a       # run every hook on every file
uv run ruff check . && uv run ruff format .
uv run ty check
```

`.claude/` contains a project plugin that makes Claude Code use `ty server` as
its Python language server.

## Access control

Users are granted access per tribe in the admin (**Users → Tribe access**).
Membership alone grants read access; `can_edit` and `can_export` are per tribe.
Superusers can do everything. Users with no tribe membership cannot sign in.

## Layout

| Path | What |
|---|---|
| `buffalo/models.py` | Animals, condition reports, samples, attachments, lookups, tribe memberships |
| `buffalo/permissions.py` | `TribeAccess`: every query is scoped through it |
| `buffalo/views.py` | Page, htmx partials, dialogs, uploads, CSV export, change history |
| `buffalo/forms.py` | Forms and validation rules carried over from the original service layer |
| `templates/cotton/` | shadcn components (vendored by `django_shadcn add …`; edit freely) |
| `templates/buffalo/partials/` | htmx fragments |
| `tailwind/source.css` | Tailwind entry point and shadcn theme |

Files are stored on the local filesystem (`MEDIA_ROOT`) and always served
through permission-checked views, never from a public `/media/` URL. To move to
S3-compatible storage, install `django-storages` and change
`STORAGES["default"]` in `config/settings.py`.
