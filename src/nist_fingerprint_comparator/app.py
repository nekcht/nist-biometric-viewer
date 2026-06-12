"""Compatibility entry point for the legacy module path."""

from nist_biometric_viewer.app import main


if __name__ == "__main__":
    raise SystemExit(main())