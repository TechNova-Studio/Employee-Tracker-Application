# Migrations

`0001_initial.py` is included in this corrected handover. IT should run only:

```bat
python manage.py migrate
python manage.py seed_demo_data
```

Do not depend on `makemigrations` during staging go-live. `makemigrations` should be used only later when developers intentionally change models.
