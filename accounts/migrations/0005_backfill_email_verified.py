from django.db import migrations


def mark_existing_profiles_verified(apps, schema_editor):
    # Accounts created before email verification existed shouldn't be locked
    # out retroactively - only new registrations go through the gate.
    Profile = apps.get_model("accounts", "Profile")
    Profile.objects.update(email_verified=True)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_profile_email_verified'),
    ]

    operations = [
        migrations.RunPython(mark_existing_profiles_verified, noop_reverse),
    ]
