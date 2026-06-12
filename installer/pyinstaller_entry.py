"""PyInstaller entry point that imports the application as a package."""

from nist_biometric_viewer.app import main

if __name__ == "__main__":
    raise SystemExit(main())
