#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
    # Ensure Python stdlib directory appears before project root on sys.path
    # so stdlib modules (like `platform`) are preferred over local packages
    try:
        import sysconfig
        stdlib = sysconfig.get_paths().get('stdlib')
        if stdlib and stdlib not in sys.path:
            sys.path.insert(0, stdlib)
    except Exception:
        pass
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
