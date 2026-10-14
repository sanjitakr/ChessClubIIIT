# IIIT Chess Club

A Django chess platform for the IIIT Chess Club.

It supports online chess, tournament management, live lobbies, offline tournament result entry, staff roles, newsletters, leaderboards, and admin tools.

## Main Features

- Online chess matches with WebSockets
- Chess lobby with live challenge updates
- Timers for online games
- Legal move validation with `python-chess`
- SAN move history for readable notation
- Draw offers, resign, and abort before first move
- Online and offline tournaments
- Swiss, round-robin, random, and custom tournament formats
- Offline result correction before the next round is paired
- Tournament time controls
- Staff portal for tournament operations
- Superadmin role management
- Compact audit logs for important admin actions
- Leaderboard and player results
- Newsletter pages
- CAS login button kept for future production integration

## Tech Stack

- Python
- Django
- Django Channels
- Daphne
- Redis
- SQLite by default
- Optional MySQL support
- WhiteNoise for static files

## Requirements

- Python 3.11 or newer
- Redis server for WebSocket/channel support
- Git

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
.\.venv\Scripts\activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
DJANGO_KEY=change-this-secret-key
DEBUG=True
REDIS_URL=redis://127.0.0.1:6379/0
```

Optional MySQL/database URL:

```env
DATABASE_URL=mysql://user:password@host:3306/database_name
```

## Database

Apply migrations:

```bash
python manage.py migrate
```

Create an admin user:

```bash
python manage.py createsuperuser
```

Create default staff groups:

```bash
python manage.py setup_roles
```

Create a normal player account:

```bash
python manage.py manage_accounts --create --username player1 --password "strong-password" --email player1@example.com
```

Create a result staff account:

```bash
python manage.py manage_accounts --create --username scorer1 --password "strong-password" --role result_staff
```

Create a tournament manager account:

```bash
python manage.py manage_accounts --create --username manager1 --password "strong-password" --role manager
```

Create a Django admin account:

```bash
python manage.py manage_accounts --create --username admin1 --password "strong-password" --role admin
```

Create a superadmin account:

```bash
python manage.py manage_accounts --create --username owner1 --password "strong-password" --role superadmin
```

Promote an existing user:

```bash
python manage.py manage_accounts --username username --role result_staff
python manage.py manage_accounts --username username --role manager
python manage.py manage_accounts --username username --role admin
python manage.py manage_accounts --username username --role superadmin
```

Remove access:

```bash
python manage.py manage_accounts --username username --remove-role result_staff
python manage.py manage_accounts --username username --remove-role manager
python manage.py manage_accounts --username username --remove-role admin
python manage.py manage_accounts --username username --remove-role superadmin
python manage.py manage_accounts --username username --remove-role all_staff
```

List staff and admin users:

```bash
python manage.py manage_accounts --list-staff
```

Older helper command for superadmin promotion:

```bash
python manage.py setup_roles --assign-superadmin username
```

Other role helpers:

```bash
python manage.py setup_roles --assign-manager username
python manage.py setup_roles --assign-staff username
```

## Run Locally

Start Redis first.

Then run the Django development server:

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

If port `8000` is already busy, use another port:

```bash
python manage.py runserver 8001
```

## Important URLs

- Home: `/`
- Login: `/login/`
- Admin: `/admin/`
- Match lobby: `/match/lobby/`
- Tournaments: `/tournaments/`
- Staff portal: `/tournaments/staff/`
- Staff role changes: `/tournaments/staff/role/`
- Newsletters: `/newsletters/`

## Roles

### Result Staff

Can record tournament results from the staff portal.

Does not get Django admin/database access.

### Tournament Manager

Can create tournaments, create newsletters, manage pairings, update time controls, and run tournament operations from the staff portal.

Does not get Django admin/database access.

### Django Admin

Can access `/admin/`.

This is separate from Result Staff and Tournament Manager.

### Superadmin

Can access `/admin/`, manage staff roles, disable staff accounts, end tournaments, and view compact audit logs.

## Tournament Rules

### Online Tournaments

Online tournament games use the match system for results and timers.

### Offline Tournaments

Offline tournaments allow staff to enter results manually.

Offline results can be corrected only before the next round pairing is generated.

## Static Files

Collect static files for production:

```bash
python manage.py collectstatic --noinput
```

Compressed static files are stored in `staticfiles/`.

## Checks And Tests

Run Django checks:

```bash
python manage.py check
```

Run tests:

```bash
python manage.py test
```

Run focused tests:

```bash
python manage.py test match tournaments
```

Check pending migrations:

```bash
python manage.py makemigrations --check --dry-run
```

## Production Notes

- Set `DEBUG=False`
- Use a strong `DJANGO_KEY`
- Use a real Redis instance
- Use MySQL or another production database if SQLite is not enough
- Run `python manage.py migrate` after deployment
- Run `python manage.py collectstatic --noinput`
- Keep CAS login integration behind the current login button until production CAS is ready

## Current Status

The app is built as a chess-club platform with live online games and tournament operations. Game analysis storage and engine-evaluation pages have been removed to reduce memory and database usage.
