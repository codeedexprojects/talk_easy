#!/usr/bin/env python3
"""
find_old_manager_roles.py
─────────────────────────
Scans the project directory for references to the old role strings:
  - 'manager_user'
  - 'manager_executive'

Usage:
    python scripts/find_old_manager_roles.py [--root /path/to/project]

Output:
    Lists every file + line number where these strings appear so you can
    update views, serializers, templates, and frontend code.
"""

import os
import sys
import argparse
import fnmatch

# ── Config ────────────────────────────────────────────────────────────────────

OLD_ROLE_STRINGS = ['manager_user', 'manager_executive']

# Extensions to scan
INCLUDE_EXTENSIONS = {
    '.py', '.html', '.js', '.jsx', '.ts', '.tsx',
    '.json', '.yaml', '.yml', '.md', '.txt', '.env',
    '.env.example', '.conf', '.sh',
}

# Directories / patterns to skip
EXCLUDE_DIRS = {
    'venv', '.git', '__pycache__', 'node_modules', '.next',
    'staticfiles', 'media', 'dist', 'build', '.tox',
    'migrations',  # Remove this if you want to scan migration files too
}


# ── Scanner ───────────────────────────────────────────────────────────────────

def should_skip_dir(dirname):
    return dirname in EXCLUDE_DIRS or dirname.startswith('.')


def scan_file(filepath, results):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for lineno, line in enumerate(f, start=1):
                for role in OLD_ROLE_STRINGS:
                    if role in line:
                        results.append({
                            'file': filepath,
                            'line': lineno,
                            'role': role,
                            'content': line.rstrip(),
                        })
    except (PermissionError, IsADirectoryError):
        pass


def scan_project(root):
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in INCLUDE_EXTENSIONS:
                scan_file(os.path.join(dirpath, filename), results)
    return results


def main():
    parser = argparse.ArgumentParser(description='Find old manager role references in codebase.')
    parser.add_argument(
        '--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        help='Root directory to scan (default: project root)',
    )
    parser.add_argument(
        '--include-migrations', action='store_true',
        help='Also scan Django migration files (disabled by default)',
    )
    args = parser.parse_args()

    if args.include_migrations:
        EXCLUDE_DIRS.discard('migrations')

    print(f"\n{'='*70}")
    print(f"  Scanning for old manager role references in: {args.root}")
    print(f"  Looking for: {OLD_ROLE_STRINGS}")
    print(f"{'='*70}\n")

    results = scan_project(args.root)

    if not results:
        print("✅  No references found! Your codebase is clean.\n")
        return

    # Group by role string
    by_role = {}
    for r in results:
        by_role.setdefault(r['role'], []).append(r)

    total = 0
    for role, matches in by_role.items():
        print(f"\n{'─'*70}")
        print(f"  Role: '{role}'  ({len(matches)} occurrence(s))")
        print(f"{'─'*70}")
        for m in matches:
            rel_path = os.path.relpath(m['file'], args.root)
            print(f"  {rel_path}:{m['line']}")
            print(f"    → {m['content']}")
        total += len(matches)

    print(f"\n{'='*70}")
    print(f"  TOTAL: {total} reference(s) to old manager roles found.")
    print(f"  Update these to use role='manager' + custom_permissions['manager_level'].")
    print(f"{'='*70}\n")

    # Exit with non-zero if any found (useful for CI pipelines)
    sys.exit(1 if results else 0)


if __name__ == '__main__':
    main()
