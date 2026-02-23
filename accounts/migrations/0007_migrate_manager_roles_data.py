# Data migration — safely migrates manager_user and manager_executive records
# to the unified 'manager' role, storing the original level in custom_permissions.
#
# This migration IS reversible:
#   - reverse reads custom_permissions['manager_level'] to restore original roles.
#
# Production safety:
#   - Uses atomic=True (default) so the whole migration is one DB transaction.
#   - Uses Apps.get_model() to work with the historical model state.

from django.db import migrations


def migrate_manager_roles(apps, schema_editor):
    """
    Forward: migrate manager_user / manager_executive → manager.
    Preserves old level in custom_permissions['manager_level'].
    """
    Admin = apps.get_model('accounts', 'Admin')
    db_alias = schema_editor.connection.alias

    # Migrate manager_executive
    exec_qs = Admin.objects.using(db_alias).filter(role='manager_executive')
    migrated_exec = 0
    for admin in exec_qs.iterator():
        # custom_permissions may be a list (old format) or dict
        if isinstance(admin.custom_permissions, list):
            # Convert list-based permissions to a dict with the old list preserved
            perms = {'legacy_permissions': admin.custom_permissions}
        elif isinstance(admin.custom_permissions, dict):
            perms = dict(admin.custom_permissions)
        else:
            perms = {}

        perms['manager_level'] = 'executive'
        perms['migrated_from'] = 'manager_executive'
        admin.role = 'manager'
        admin.custom_permissions = perms
        admin.save(update_fields=['role', 'custom_permissions'])
        migrated_exec += 1

    # Migrate manager_user
    user_qs = Admin.objects.using(db_alias).filter(role='manager_user')
    migrated_user = 0
    for admin in user_qs.iterator():
        if isinstance(admin.custom_permissions, list):
            perms = {'legacy_permissions': admin.custom_permissions}
        elif isinstance(admin.custom_permissions, dict):
            perms = dict(admin.custom_permissions)
        else:
            perms = {}

        perms['manager_level'] = 'user'
        perms['migrated_from'] = 'manager_user'
        admin.role = 'manager'
        admin.custom_permissions = perms
        admin.save(update_fields=['role', 'custom_permissions'])
        migrated_user += 1

    print(
        f"\n  [0007] Migrated {migrated_exec} manager_executive → manager (executive level)"
        f"\n  [0007] Migrated {migrated_user} manager_user → manager (user level)"
    )


def reverse_migrate_manager_roles(apps, schema_editor):
    """
    Reverse: restore manager → manager_user / manager_executive
    based on custom_permissions['manager_level'].
    """
    Admin = apps.get_model('accounts', 'Admin')
    db_alias = schema_editor.connection.alias

    manager_qs = Admin.objects.using(db_alias).filter(role='manager')
    restored = 0
    for admin in manager_qs.iterator():
        perms = admin.custom_permissions if isinstance(admin.custom_permissions, dict) else {}
        level = perms.get('manager_level')
        original_role = perms.get('migrated_from')

        if original_role in ('manager_executive', 'manager_user'):
            admin.role = original_role
        elif level == 'executive':
            admin.role = 'manager_executive'
        elif level == 'user':
            admin.role = 'manager_user'
        else:
            # Cannot determine original, leave as manager
            continue

        # Clean up migration metadata
        perms.pop('manager_level', None)
        perms.pop('migrated_from', None)
        if 'legacy_permissions' in perms and not perms.get('legacy_permissions'):
            perms.pop('legacy_permissions', None)

        admin.custom_permissions = perms
        admin.save(update_fields=['role', 'custom_permissions'])
        restored += 1

    print(f"\n  [0007 reverse] Restored {restored} manager → original roles")


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_admin_role_choices'),
    ]

    operations = [
        migrations.RunPython(
            migrate_manager_roles,
            reverse_code=reverse_migrate_manager_roles,
        ),
    ]
