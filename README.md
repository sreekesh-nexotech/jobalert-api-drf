# JobAlert API

Django + Django REST Framework backend for the JobAlert mobile app.
Provides authentication, job & business listings, engagement (upvotes,
comments, saves), points/rewards, subscriptions, and admin moderation.

## Stack

- **Python 3.11+**, **Django 5.x**, **Django REST Framework 3.15+**
- **JWT** auth via `djangorestframework-simplejwt`
- **drf-spectacular** for OpenAPI 3.1 schema, Swagger UI, ReDoc
- **django-filter** for query filtering
- **PostgreSQL** in production, SQLite for local dev
- **python-decouple** for environment configuration

## Project Layout

```
config/         # project package — settings, urls, pagination, exceptions
core/           # single app — all 14 models, serializers, views, filters
manage.py
requirements.txt
```

## Getting Started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

API is served at `http://localhost:8000/api/v1/`.
Swagger UI at `http://localhost:8000/api/docs/`.
OpenAPI schema at `http://localhost:8000/api/schema/`.

## Key Endpoints

| Group | Path | Methods |
|-------|------|---------|
| Auth | `/api/v1/auth/register/` | POST (issues JWT + emails signup OTP) |
| Auth | `/api/v1/auth/login/` | POST (email **or** mobile) |
| Auth | `/api/v1/auth/refresh/` | POST |
| Auth | `/api/v1/auth/logout/` | POST |
| Auth | `/api/v1/auth/change-password/` | POST |
| Auth | `/api/v1/auth/otp/send/` | POST |
| Auth | `/api/v1/auth/otp/verify/` | POST |
| Auth | `/api/v1/auth/password-reset/request/` | POST |
| Auth | `/api/v1/auth/password-reset/confirm/` | POST |
| Users | `/api/v1/users/me/` | GET, PATCH |
| Users | `/api/v1/users/me/avatar/` | POST (multipart) |
| Users | `/api/v1/users/me/stats/` | GET |
| Users | `/api/v1/users/me/request-deletion/` | POST |
| Users | `/api/v1/user-details/` | CRUD |
| Home | `/api/v1/home/feed/` | GET (personalised aggregate) |
| Listings | `/api/v1/job-listings/` | CRUD |
| Listings | `/api/v1/job-listings/{uid}/upvote/` | POST, DELETE |
| Listings | `/api/v1/job-listings/{uid}/save/` | POST, DELETE |
| Listings | `/api/v1/job-listings/{uid}/apply/` | POST |
| Listings | `/api/v1/job-listings/{uid}/view/` | POST |
| Listings | `/api/v1/job-listings/{uid}/approve/` `…/reject/` | POST (admin) |
| Listings | `/api/v1/biz-listings/` | CRUD (same actions as job-listings) |
| Listings | `/api/v1/listings/can-submit/` | GET (plus-button gate) |
| Engagement | `/api/v1/comments/` | CRUD |
| Engagement | `/api/v1/comments/{uid}/like/` | POST, DELETE |
| Engagement | `/api/v1/upvotes/` | List, Read |
| User Data | `/api/v1/saved-listings/` | List |
| User Data | `/api/v1/points/history/` | List |
| Subs | `/api/v1/subscriptions/` | CRUD |
| Notifications | `/api/v1/notifications/` | List, Read |
| Notifications | `/api/v1/notifications/unread-count/` | GET |
| Notifications | `/api/v1/notifications/{uid}/read/` | POST |
| Notifications | `/api/v1/notifications/mark-all-read/` | POST |
| Filters | `/api/v1/filter-prefs/` | CRUD |
| Files | `/api/v1/files/` | CRUD |
| Reports | `/api/v1/reports/` | CRUD + admin `/review/` |
| Activity | `/api/v1/activity-logs/` | POST (any), List/Read (admin) |
| App Meta | `/api/v1/app-meta/` | CRUD (read public) |
| Static Pages | `/api/v1/static-pages/` | CRUD by slug; admin write, public read |

## Conventions

- All resources are looked up by their `uid` UUID, never the internal `id`.
- All endpoints are versioned under `/api/v1/`.
- Standard envelope on errors: `{"code": <int>, "message": <str>, "errors": <obj?>}`.
- Page size is 20 by default (`?page_size=` overrides up to 100).
- Filtering: `?<field>=<value>`. Searching: `?search=<term>`. Ordering: `?ordering=<field>`.

## Operations

- `python manage.py cleanup_otps` — schedule via cron / systemd / Celery beat.
  Removes expired codes and used codes older than 7 days
  (`--keep-used-for-days N` to override; `--dry-run` to preview).
- `python manage.py create_admin` — idempotent. Promotes / refreshes the
  default administrator account from `DEFAULT_ADMIN_*` env vars.

## Deploying

- `python manage.py migrate` on every deploy (auto-creates the default admin).
- `python manage.py collectstatic --noinput` once per deploy (Swagger/admin assets).
- Set `DJANGO_DEBUG=False` and `DJANGO_ALLOWED_HOSTS=<your-host>`.
- `MEDIA_ROOT` (default `./media/`) needs persistent storage for avatar uploads.
  In production, swap to S3/Bunny/Cloudinary by changing
  `DEFAULT_FILE_STORAGE` — `AvatarUploadView` already returns whatever
  `default_storage.url()` produces.
- Schedule `cleanup_otps` (e.g. nightly).
- For Flutter web later, append origins to `CORS_ALLOWED_ORIGINS`.
