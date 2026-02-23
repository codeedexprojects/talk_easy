# Schema migration — updates Django choices metadata for the `role` field.
# No DB column change is required; choices are metadata only in SQLite/PostgreSQL.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_adminotp'),
    ]

    operations = [
        migrations.AlterField(
            model_name='admin',
            name='role',
            field=models.CharField(
                choices=[
                    ('hr_user', 'HR - User'),
                    ('hr_executive', 'HR - Executive'),
                    ('manager', 'Manager'),
                    ('superuser', 'Superuser'),
                    ('other', 'Other'),
                ],
                default='other',
                max_length=20,
            ),
        ),
    ]
