#!/usr/bin/env python
"""
Development server runner for Zenzefi Backend.

This script can be used in two ways:
1. Direct run: python run_dev.py (auto-detects Poetry environment)
2. PyCharm/VSCode: Configure interpreter to use Poetry virtualenv

The script automatically checks if running in Poetry environment
and provides helpful error messages if dependencies are missing.
"""
import sys
import os
from pathlib import Path


def check_poetry_env():
    """Check if running in Poetry virtual environment"""
    # Check if we're in a virtual environment
    in_venv = hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )

    # Check if apscheduler is available
    try:
        import apscheduler
        return True
    except ImportError:
        return False


def get_poetry_python():
    """Get path to Poetry's Python interpreter"""
    import subprocess
    try:
        result = subprocess.run(
            ["poetry", "env", "info", "--path"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).parent
        )
        venv_path = result.stdout.strip()

        # Construct Python path based on OS
        if sys.platform == "win32":
            python_path = Path(venv_path) / "Scripts" / "python.exe"
        else:
            python_path = Path(venv_path) / "bin" / "python"

        return str(python_path)
    except Exception as e:
        return None


def main():
    """Run development server with proper environment"""

    # Check if we're in the correct environment
    if not check_poetry_env():
        print("[WARNING] Dependencies not found in current Python environment!")
        print(f"          Current Python: {sys.executable}")
        print()

        # Try to get Poetry environment
        poetry_python = get_poetry_python()

        if poetry_python and Path(poetry_python).exists():
            print("[OK] Found Poetry virtual environment")
            print(f"     Restarting with: {poetry_python}")
            print()

            # Re-run this script with Poetry's Python
            import subprocess
            result = subprocess.run(
                [poetry_python, __file__],
                cwd=Path(__file__).parent
            )
            sys.exit(result.returncode)
        else:
            print("[ERROR] Could not find Poetry virtual environment!")
            print()
            print("Please run one of the following:")
            print("  1. poetry run python run_dev.py")
            print("  2. poetry install && poetry run python run_dev.py")
            print("  3. Configure your IDE to use Poetry interpreter:")
            print("     - PyCharm: Settings -> Project -> Python Interpreter -> Add -> Poetry Environment")
            print("     - VSCode: Select Poetry interpreter in bottom-left corner")
            print()
            sys.exit(1)

    # Dependencies are available, run the server
    print("[OK] Running in Poetry virtual environment")
    print(f"     Python: {sys.executable}")
    print()

    try:
        import uvicorn

        # Run the development server
        print("=" * 60)
        print("Starting Zenzefi Backend development server...")
        print("=" * 60)
        print("URL:    http://0.0.0.0:8000")
        print("Docs:   http://0.0.0.0:8000/docs")
        print("Health: http://0.0.0.0:8000/health")
        print("=" * 60)
        print()

        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info",
        )
    except KeyboardInterrupt:
        print("\n[OK] Server stopped")
    except Exception as e:
        print(f"\n[ERROR] Error starting server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
