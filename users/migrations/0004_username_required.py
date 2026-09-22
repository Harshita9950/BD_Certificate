import re

from django.db import migrations, models


def _derive_username(email: str, existing: set) -> str:
    """
    Derive a unique username from an email address.
    Takes the local part (before @), strips non-alphanumeric/underscore/dot
    characters, lowercases, and appends a numeric suffix when there is a
    collision.
    """
    local = email.split('@')[0]
    base  = re.sub(r'[^\w.]', '', local).lower().strip('.')[:120] or 'user'

    candidate = base
    counter   = 1
    while candidate in existing:
        candidate = f'{base}_{counter}'
        counter  += 1

    existing.add(candidate)
    return candidate


def populate_usernames(apps, schema_editor):
    User = apps.get_model('users', 'User')

    existing_usernames = set(
        User.objects.exclude(username__isnull=True)
                    .exclude(username='')
                    .values_list('username', flat=True)
    )

    to_update = []
    for user in User.objects.filter(models.Q(username__isnull=True) | models.Q(username='')):
        user.username = _derive_username(user.email, existing_usernames)
        to_update.append(user)

    if to_update:
        User.objects.bulk_update(to_update, ['username'])


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_user_ulb_fk_user_ward_fk_user_zone_fk_and_more'),
    ]

    operations = [
        # Step 1 — allow NULL temporarily so the column can be added
        migrations.AlterField(
            model_name='user',
            name='username',
            field=models.CharField(
                max_length=150, unique=True, blank=True, null=True,
                verbose_name='username',
            ),
        ),

        # Step 2 — add username_attempted to UserLoginLog
        migrations.AddField(
            model_name='userloginlog',
            name='username_attempted',
            field=models.CharField(
                blank=True, default='', max_length=150,
                verbose_name='username attempted',
            ),
            preserve_default=False,
        ),

        # Step 3 — populate username for every existing user
        migrations.RunPython(populate_usernames, migrations.RunPython.noop),

        # Step 4 — tighten to NOT NULL + keep unique + add db_index
        migrations.AlterField(
            model_name='user',
            name='username',
            field=models.CharField(
                max_length=150, unique=True, db_index=True,
                verbose_name='username',
            ),
        ),
    ]
