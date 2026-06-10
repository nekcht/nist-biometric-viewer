# NIST Fingerprint Comparator

NIST Fingerprint Comparator is a Python Qt desktop application for reviewing biometric
images embedded in ANSI/NIST transaction files. It compares one reference File A against
an ordered queue of File B candidates, placing the same standard finger positions side by
side for visual review.

The parser is deliberately warning-based: malformed, unknown, and unsupported records are
retained where possible instead of causing the entire transaction to fail.

## Features

- Professional PySide6 desktop interface with a transaction summary and warning sidebar
- Single-step setup for File A and the complete File B candidate group
- Responsive background parsing and decoding with an animated loading screen
- Same-position File A/File B comparison for every biometric impression
- One-to-many review queue with explicit green **MATCH** and red **NO MATCH** decisions
- Persistent internal SQLite decision history shared by all future review sessions
- Filterable XLSX decision-history export and professional menu/icon toolbar
- Cross-file rows for individual fingers, plain impressions, slaps, palms, combined
  captures, duplicates, and unknown position codes
- Zoomable and pannable in-memory image previews
- Compact record and capture metadata for every image
- Clear placeholders for missing or undecodable images
- Extensible parser and decoder modules

## Install

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Run

```powershell
python -m nist_fingerprint_comparator.app
```

Choose **New Comparison** and select the reference File A plus all File B candidates in
the setup dialog. The visual comparison workspace remains hidden while the reference and
first candidate load, then opens when the first complete pair is ready. An animated
loading screen is shown before the first pair and between later candidates. Parsing and
decoding happen on a worker thread, so the UI remains responsive.

For each candidate, choose **MATCH** or **NO MATCH** after visual review. The choice is
committed immediately to one internal SQLite history database before the next candidate is
loaded. `NO MATCH` is stored as `NO_MATCH`. The minimal internal record includes the UTC
timestamp, decision, filenames, SHA-256 file identifiers, and transaction control numbers.
After the last decision is recorded, the application clears the completed session and
returns to the initial New Comparison screen.

Use **File > Export Decision History** to export the complete history, or an optional UTC
date/time range, to a formatted XLSX workbook. The export dialog defaults to the Desktop.

The application is for visual review only. It does not perform biometric matching,
similarity scoring, or identity verification.

## MVP Support

- Type-1 transaction metadata
- Type-2 descriptive metadata
- Type-13 latent image records
- Type-14 fingerprint image records
- Type-15 palm image records
- Best-effort exposure of legacy binary Type-4 records
- JPEG, PNG, and JPEG2000 through the installed Pillow build
- WSQ decoding through the declared `wsq` Pillow plugin dependency

Tagged image records use common ANSI/NIST fields for IDC, impression type, source agency,
capture date, dimensions, scale, compression, bit depth, position, quality, and `.999`
image data. Profile-specific fields remain available as raw metadata.

## Limitations

- WSQ decoding uses the declared `wsq` Pillow plugin. The application reports unsupported
  WSQ images without crashing if the plugin is unavailable on the running platform.
- Type-4 parsing is partial because legacy binary layouts and encodings need additional
  profile-specific handling.
- JPEG2000 support depends on the capabilities of the installed Pillow build.
- ANSI/NIST versions and agency profiles vary. Unknown records and fields are retained or
  reported as warnings where practical.
- Slaps, palms, latents, combined captures, unknown position codes, and duplicate records
  are displayed as File A versus File B comparison rows. Missing-position records remain
  visible as one-sided rows. The application does not automatically match or score them.

## Security And Privacy

Biometric data must be handled according to applicable law, organizational policy, and
access-control requirements. The application does not write embedded or decoded biometric
images to disk by default, and image bytes are excluded from logs and model
representations. The internal SQLite history and exported XLSX workbooks contain
identifiers and decisions and must be protected accordingly. Avoid sharing logs,
transaction files, or exports unless explicitly authorized.

## Development

```powershell
pytest
ruff check .
```

The package follows a `src` layout:

- `core`: domain models and pairing rules
- `nist`: separators, tagged-field parsing, and record conversion
- `imaging`: decoder selection and in-memory image conversion
- `ui`: Qt widgets and background worker

## Roadmap

- Full binary Type-4 field and compression support
- Additional agency profile adapters and record types
- Configurable WSQ/NBIS backend
- Optional human-directed comparison tools for palms, slaps, and latent impressions
- Synchronized image zoom and pan
- Explicit, policy-aware report export
