#!/bin/bash

# Django Loan Management System - Development Setup Script
# This script installs all dependencies and sets up the development environment

echo "🚀 Setting up Django Loan Management System..."

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo "❌ Error: Please run this script from the project root directory (where manage.py is located)"
    exit 1
fi

# Install system dependencies
echo "📦 Installing system dependencies..."
sudo dnf install -y python3-pip python3-devel gcc postgresql-devel libpq-devel

# Create static directory if it doesn't exist
echo "📁 Creating static directory..."
mkdir -p static

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
pip3 install -r requirements.txt

# Run Django checks
echo "🔍 Running Django system checks..."
python3 manage.py check

# Run migrations (if needed)
echo "🗄️ Running database migrations..."
python3 manage.py migrate

echo "✅ Setup complete!"
echo ""
echo "🎯 Next steps:"
echo "1. Start development server: python3 manage.py runserver 0.0.0.0:8000"
echo "2. Access admin interface: http://localhost:8000/admin/"
echo "3. Create superuser: python3 manage.py createsuperuser"
echo ""
echo "📚 Project documentation:"
echo "- Admin interface: http://localhost:8000/admin/"
echo "- API documentation: http://localhost:8000/api/"
echo "- Django settings: config/settings.py"
