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
| Auth | `/api/v1/auth/register/` | POST |
| Auth | `/api/v1/auth/login/` | POST |
| Auth | `/api/v1/auth/refresh/` | POST |
| Auth | `/api/v1/auth/logout/` | POST |
| Users | `/api/v1/users/me/` | GET, PATCH |
| Users | `/api/v1/user-details/` | CRUD |
| Listings | `/api/v1/job-listings/` | CRUD |
| Listings | `/api/v1/job-listings/{uid}/upvote/` | POST, DELETE |
| Listings | `/api/v1/job-listings/{uid}/save/` | POST, DELETE |
| Listings | `/api/v1/job-listings/{uid}/apply/` | POST |
| Listings | `/api/v1/biz-listings/` | CRUD |
| Engagement | `/api/v1/comments/` | CRUD |
| Engagement | `/api/v1/upvotes/` | List, Read |
| User Data | `/api/v1/saved-listings/` | List |
| User Data | `/api/v1/applied-listings/` | List |
| User Data | `/api/v1/points/history/` | List |
| Subs | `/api/v1/subscriptions/` | CRUD |
| Filters | `/api/v1/filter-prefs/` | CRUD |
| Files | `/api/v1/files/` | CRUD |
| Reports | `/api/v1/reports/` | CRUD |
| Activity | `/api/v1/activity-logs/` | List, Read (admin) |
| App Meta | `/api/v1/app-meta/` | CRUD (read public) |

## Conventions

- All resources are looked up by their `uid` UUID, never the internal `id`.
- All endpoints are versioned under `/api/v1/`.
- Standard envelope on errors: `{"code": <int>, "message": <str>, "errors": <obj?>}`.
- Page size is 20 by default (`?page_size=` overrides up to 100).
- Filtering: `?<field>=<value>`. Searching: `?search=<term>`. Ordering: `?ordering=<field>`.
