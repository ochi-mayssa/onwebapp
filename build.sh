#!/usr/bin/env bash
set -o errexit

echo "🚀 Starting build process..."

# Install dependencies
pip install -r requirements.txt

# Create staticfiles directory if it doesn't exist
echo "📁 Creating staticfiles directory..."
mkdir -p staticfiles

# Collect static files
echo "📦 Collecting static files..."
python manage.py collectstatic --no-input

# Create migrations if needed
echo "📝 Creating migrations..."
python manage.py makemigrations --no-input || true

# Apply migrations
echo "🔄 Applying database migrations..."
python manage.py migrate --no-input

echo "✅ Build completed successfully!"
