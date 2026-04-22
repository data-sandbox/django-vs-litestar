import os
import sys


def main() -> None:
    """Run Django's command-line management utility."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_api.config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError("Django must be installed.") from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
