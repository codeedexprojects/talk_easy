#!/usr/bin/env python3
"""
migrate_manager_permissions.py
─────────────────────────────
Helper script to inspect and/or apply custom_permissions migration for managers.

This script connects directly to the Django database and:
  1. Shows all current manager records and their custom_permissions (preview mode).
  2. Optionally updates custom_permissions for records missing 'manager_level'.
  3. Verifies no rows with role='manager_user' or 'manager_executive' remain.

Usage:
    # Preview only (no changes)
    python scripts/migrate_manager_permissions.py

    # Apply: fill in missing manager_level based on migrated_from field
    python scripts/migrate_manager_permissions.py --apply

    # Verify: check that no old roles remain in the database
    python scripts/migrate_manager_permissions.py --verify

Prerequisites:
    - Django apps configured in DJANGO_SETTINGS_MODULE environment variable.
    - Run from the project root directory with venv activated.

    cd /home/muhammed-fazal/Desktop/talk_easy
    source venv/bin/activate
    python scripts/migrate_manager_permissions.py --verify
"""

import os
import sys
import argparse
import json

# ── Django setup ──────────────────────────────────────────────────────────────
# Add project root to sys.path so Django settings can be found.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'talkeasy.settings')

import django
django.setup()

from django.db import transaction
from accounts.models import Admin


# ── Helpers ───────────────────────────────────────────────────────────────────

DIVIDER = '─' * 72


def format_perms(perms):
    if isinstance(perms, dict):
        return json.dumps(perms, indent=2)
    return repr(perms)


def preview():
    """Show all managers and their current permissions."""
    managers = Admin.objects.filter(role='manager').order_by('id')
    old_exec = Admin.objects.filter(role='manager_executive').count()
    old_user = Admin.objects.filter(role='manager_user').count()

    print(f"\n{DIVIDER}")
    print(f"  PREVIEW — Manager Records")
    print(f"{DIVIDER}")
    print(f"  Total managers (role='manager'): {managers.count()}")
    print(f"  ⚠️  Remaining manager_executive rows: {old_exec}")
    print(f"  ⚠️  Remaining manager_user rows:      {old_user}")
    print()

    for mgr in managers:
        level = mgr.custom_permissions.get('manager_level', '⚠️  NOT SET') \
            if isinstance(mgr.custom_permissions, dict) else '⚠️  NOT SET (non-dict)'
        print(f"  ID={mgr.id:4d}  {mgr.email:<35s}  level={level}")
        print(f"           custom_permissions: {format_perms(mgr.custom_permissions)}")

    if old_exec or old_user:
        print(f"\n  ❌ Old role rows still exist. Run the Django migration first:")
        print(f"     python manage.py migrate accounts")
    else:
        print(f"\n  ✅ No old role rows found.")

    print(f"{DIVIDER}\n")
    return managers


def apply_fix():
    """
    For any manager row missing 'manager_level' in custom_permissions,
    attempt to infer it from 'migrated_from' or default to 'user'.

    This is a safety net for edge cases where the data migration
    could not determine the original level.
    """
    managers = Admin.objects.filter(role='manager')
    fixed = 0

    with transaction.atomic():
        for mgr in managers.iterator():
            perms = mgr.custom_permissions if isinstance(mgr.custom_permissions, dict) else {}
            if 'manager_level' not in perms:
                # Infer from migrated_from if available
                original = perms.get('migrated_from', '')
                if original == 'manager_executive':
                    inferred = 'executive'
                else:
                    inferred = 'user'  # safe default

                perms['manager_level'] = inferred
                if isinstance(mgr.custom_permissions, list):
                    perms['legacy_permissions'] = mgr.custom_permissions
                mgr.custom_permissions = perms
                mgr.save(update_fields=['custom_permissions'])
                print(f"  Fixed ID={mgr.id} ({mgr.email}): set manager_level='{inferred}'")
                fixed += 1

    print(f"\n  ✅ Fixed {fixed} record(s).\n")


def verify():
    """Verify no old roles remain and all managers have manager_level set."""
    old_exec = Admin.objects.filter(role='manager_executive').count()
    old_user = Admin.objects.filter(role='manager_user').count()
    total_managers = Admin.objects.filter(role='manager').count()

    missing_level = 0
    for mgr in Admin.objects.filter(role='manager').iterator():
        perms = mgr.custom_permissions if isinstance(mgr.custom_permissions, dict) else {}
        if 'manager_level' not in perms:
            missing_level += 1
            print(f"  ⚠️  ID={mgr.id} ({mgr.email}) is missing 'manager_level' in custom_permissions")

    print(f"\n{DIVIDER}")
    print(f"  VERIFICATION REPORT")
    print(f"{DIVIDER}")
    print(f"  Total managers:                   {total_managers}")
    print(f"  Old 'manager_executive' rows:     {old_exec}  {'✅' if old_exec == 0 else '❌'}")
    print(f"  Old 'manager_user' rows:          {old_user}  {'✅' if old_user == 0 else '❌'}")
    print(f"  Managers missing manager_level:   {missing_level}  {'✅' if missing_level == 0 else '❌'}")

    all_ok = (old_exec == 0 and old_user == 0 and missing_level == 0)
    if all_ok:
        print(f"\n  ✅ All checks passed! Migration is complete and clean.")
    else:
        print(f"\n  ❌ Issues found. Run:")
        if old_exec or old_user:
            print(f"       python manage.py migrate accounts")
        if missing_level:
            print(f"       python scripts/migrate_manager_permissions.py --apply")
    print(f"{DIVIDER}\n")

    return all_ok


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Migration helper: inspect and fix manager custom_permissions.',
    )
    parser.add_argument('--apply', action='store_true',
                        help='Fill in missing manager_level values (safe, atomic).')
    parser.add_argument('--verify', action='store_true',
                        help='Verify migration is complete and no old roles remain.')
    args = parser.parse_args()

    if args.verify:
        ok = verify()
        sys.exit(0 if ok else 1)
    elif args.apply:
        print(f"\n{DIVIDER}")
        print(f"  APPLY MODE — Fixing missing manager_level entries")
        print(f"{DIVIDER}\n")
        apply_fix()
        verify()
    else:
        preview()


if __name__ == '__main__':
    main()
