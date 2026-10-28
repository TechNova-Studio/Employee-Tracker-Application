# Create only the initial Super Admin

The production bootstrap creates one Django User and its WorkPulse Profile:

- User.is_superuser, User.is_staff and User.is_active are true.
- Profile.role is SUPER_ADMIN; the profile is active and can manage trial setup.
- The administrator has no company, department, manager or employee display code.
- The password is validated and saved as a Django password hash.

No companies, employees, plans, trial codes or demo records are seeded. Django's
normal migrations still create the application's tables and authentication
metadata. An existing matching active platform Super Admin is reused unchanged.
Existing employee accounts are never silently promoted, and this bootstrap
rejects creating another initial administrator when one already exists.

## Install the patch

Extract `workpulse_superadmin_bootstrap.zip` into the existing `bold-workpulse`
folder. Copy the included backend/core files together: migration 0006 imports
the included versioned helper. Existing settings.py and database credentials
do not need to be replaced.

## Option A: migration creates the account

Before applying migration 0006, set your chosen credentials in the project's
root `.env` or in the process environment:

```env
WORKPULSE_SUPERADMIN_EMAIL=YOUR_ADMIN_EMAIL
WORKPULSE_SUPERADMIN_PASSWORD=YOUR_CHOSEN_STRONG_PASSWORD
```

Replace both placeholders. Optionally set WORKPULSE_SUPERADMIN_USERNAME for a
different login username; otherwise the email is used as the username. The
local `.env` location is the existing project root beside `.env.example`.

From `backend`, with the Render database configuration active:

```bat
python manage.py migrate
```

This includes `core.0006_bootstrap_super_admin` and creates the administrator.
No hardcoded or shared default login credentials are included.

## Option B: hidden password prompt

With the bootstrap environment fields left empty:

```bat
python manage.py migrate
python manage.py bootstrap_super_admin --email YOUR_ADMIN_EMAIL
```

Replace YOUR_ADMIN_EMAIL with your actual administrator email. Enter your chosen
password at the two hidden prompts. This works even if migration 0006 was
already applied without credentials. Do not reverse migrations to create the
account later.

For a noninteractive terminal, set the bootstrap email/password configuration
first and run:

```bat
python manage.py bootstrap_super_admin --noinput
```

The command also supports --username and --database. Repeating it with the same
identity preserves the existing password, user ID and profile.

## Vercel and Render

Vercel environment variables apply to Vercel processes. They do not configure
the Windows terminal used to run migrations. For local migration/bootstrap,
configure the same Render external DB_HOST, DB_NAME, DB_USER, DB_PASSWORD and
DB_PORT in the project's existing root .env.

Apply migrations/bootstrap from a backend terminal connected to that database.
Do not expose a public seeding endpoint or add schema migrations to every
Vercel preview build. If using Vercel CLI to pull environment variables, ensure
the pulled values are loaded into this project's existing root .env or process
environment before running these commands.

After setup, remove the optional bootstrap password from deployment
configuration when it is no longer needed. The saved account and its password
hash remain valid. Changing the bootstrap password value does not change an
existing administrator's password; normal password management is separate.

## Verify and sign in

```bat
python manage.py showmigrations core
python manage.py shell -c "from django.contrib.auth.models import User; print(list(User.objects.filter(profile__role='SUPER_ADMIN').values('id','email','is_superuser','is_staff','profile__role','profile__company_id')))"
```

On a new database, the second command returns one administrator with
profile__company_id set to None. Sign in to the admin web using the email and
chosen password. Create the company and other records through the application.

Do not run seed_demo_data or the demo-populating Windows setup script for this
Super Admin only production setup. This bootstrap does not delete pre-existing
data. Reversing migration 0006 intentionally keeps the administrator.

## Validation

Targeted tests cover historical migration execution, account-only creation,
password validation/hashing, rollback, idempotence, conflicts with existing
accounts, hidden command prompts and admin web login. SQLite test settings are
used; the live Render database is not accessed by these tests.
