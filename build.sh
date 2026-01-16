#!/usr/bin/env bash
set -o errexit

echo "Setting up Python environment..."

# First install build essentials
python -m pip install --upgrade pip setuptools wheel

# Then install requirements
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput

# Run migrations
python manage.py migrate