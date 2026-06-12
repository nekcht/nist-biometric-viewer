# Nist Biometric Viewer

A local Windows desktop tool for visually reviewing biometric images inside ANSI/NIST
transaction files. It compares one **Reference Record** against one or more
**Comparison Records**.

The app is for visual review only. It does not perform automated biometric matching,
identity verification, or identity decisions.

Link to Windows Installer: https://drive.google.com/file/d/177gHtteaofmw9BV4uV39DkFUrj7xN1Q_/view?usp=sharing

## Current Support

ANSI/NIST records:

- Type-1 metadata
- Type-2 metadata
- Type-13 latent images
- Type-14 fingerprint images
- Type-15 palm images
- Partial, best-effort Type-4 support

Decoded image formats:

- JPEG and PNG
- JPEG2000 when supported by Pillow
- WSQ when the WSQ plugin is available

The app supports common ANSI/NIST biometric image records, mainly Type-13, Type-14, and
Type-15, with partial best-effort Type-4 support. ANSI/NIST versions and agency profiles
vary, so unsupported records or fields may appear as warnings. ZIP archives are supported;
RAR archives require a compatible extraction backend.

## Run From Source

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m nist_biometric_viewer.app
```

## Windows Build

PyInstaller builds the application bundle. Inno Setup builds the Windows setup `.exe`;
it is not an MSI installer.

```powershell
.\scripts\build_windows.ps1
.\scripts\build_installer.ps1
```

## Privacy

The app runs locally and offline and does not upload data. Biometric images are not written
to disk by default. Logs, decision history, and exported workbooks may contain sensitive
data and should be protected accordingly.

## Development

```powershell
pytest
ruff check .
```
