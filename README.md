# Nist Biometric Viewer

Nist Biometric Viewer is a Python Qt desktop application for reviewing biometric
images embedded in ANSI/NIST transaction files. It compares one Reference Record against
an ordered group of Comparison Records, placing the same standard finger positions side
by side for visual review.

The parser is deliberately warning-based: malformed, unknown, and unsupported records are
retained where possible instead of causing the entire transaction to fail.

## Features

- Professional PySide6 desktop interface with a transaction summary and warning sidebar
- Guided source and Reference Record phases that auto-detect a multi-selected or
  drag-and-dropped ANSI/NIST record group, ZIP archive, or RAR archive
- Responsive background parsing and decoding with an initial loading screen and dimmed
  in-place transitions between later pairs
- Same-position Reference Record/Comparison Record review for every biometric impression
- One-to-many review queue with **MATCH**, **NO MATCH**, and uncertain **PASS** decisions
- Previous-comparison correction and explicit end-session controls
- Persistent internal SQLite decision history shared by all future review sessions
- In-app history display, permanent history deletion, filterable XLSX export, and
  professional menu-driven controls
- Configurable timezone for recorded comparison-history timestamps
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

## Windows Installer

The production Windows build uses PyInstaller for the application bundle and Inno Setup 6
for a per-user `.exe` installer. Inno Setup does not produce an MSI package.

Required tools:

- Python 3.11 or newer with the project's `dev` dependencies
- PyInstaller
- Inno Setup 6

Build the packaged application only:

```powershell
.\scripts\build_windows.ps1
```

This creates `dist\ForensicPrintComparator\ForensicPrintComparator.exe` and its required
runtime files. Build the application and installer together with:

```powershell
.\scripts\build_installer.ps1
```

The installer build looks for ISCC at
`C:\Program Files (x86)\Inno Setup 6\ISCC.exe`. Set `ISCC_PATH` or pass `-ISCCPath` when
Inno Setup is installed elsewhere. The final installer is written to
`installer\output\NistBiometricViewer_Setup_<version>.exe`. The version comes from
`nist_fingerprint_comparator.__version__`, which is also used by package metadata and the
About dialog.

The per-user installer requires no administrator privileges. It installs application files
under `%LOCALAPPDATA%\Programs\ForensicPrintComparator` and creates these preserved folders
under `%APPDATA%\ForensicPrintComparator`:

- `config`
- `logs`
- `history`
- `exports`
- `temp`

Existing settings, logs, history, and exports are not overwritten or deleted during upgrade
or uninstall. The application also recreates missing folders at startup and copies only
missing baseline configuration files. Raw archive contents continue to use self-cleaning
system temporary directories rather than persistent application data.

The installer creates application configuration/log/history folders only. It does not
install or store biometric evidence files.

## Run

```powershell
python -m nist_fingerprint_comparator.app
```

From the initial screen, select the **+** button or immediately drag and drop the complete
ANSI/NIST record group, one ZIP archive, or one RAR archive. Select **Next**, appoint one
file as the Reference Record, then select **Next** again to begin comparison. Every other
record becomes a Comparison Record. Archives are extracted before the Reference Record
phase. Archive and record filenames do not need to follow a naming convention.

The visual comparison workspace remains hidden while the archive, Reference Record, and
first Comparison Record load, then opens when the first complete pair is ready. The initial
pair uses the dedicated loading screen. Between later Comparison Records, the current
workspace remains visible in a dimmed, disabled loading state. Archive extraction, parsing,
and decoding happen on worker threads, so the UI remains responsive. Extracted archive
files are held in a temporary session directory and deleted when the review finishes,
fails before opening, is replaced, or the application closes.

Each displayed biometric image has its own overlaid icon controls for **Zoom In**,
**Zoom Out**, and **Fit**. Images can be panned by dragging. Mouse-wheel scrolling does
not zoom images.

For each Comparison Record, choose **MATCH**, **NO MATCH**, or **PASS** after visual review. Use
**PASS** to ignore a comparison without saving it to decision history. **MATCH** and
**NO MATCH** choices are committed immediately to one internal SQLite history database
before the next Comparison Record is loaded. `NO MATCH` is stored as `NO_MATCH`.

During an active session, **Previous Comparison** warns the reviewer, undoes the immediately
preceding result, and reloads that pair for a fresh review.
**End Session** stops the remaining queue while keeping decisions already completed. Use
**View Comparison History** to display all records currently held in the internal database.
The minimal internal record includes the selected-timezone timestamp, its timezone,
canonical UTC time, decision, filenames, and transaction control numbers.
After the last decision is recorded, the application clears the completed session and
returns to the initial New Comparison screen.

Use **View Comparison History > Export History** to export the complete history, or an
optional UTC date/time range, to a formatted XLSX workbook. History export and permanent
history deletion are available only inside **View Comparison History**. Deletion requires
confirmation, and the export dialog defaults to the per-user `exports` folder.

Use **Edit > Settings** to select the timezone recorded and displayed for new history
entries. Canonical UTC timestamps are retained internally for reliable filtering.

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
- RAR extraction uses the declared `rarfile` package and requires a compatible RAR
  extraction backend on the running system.
- Type-4 parsing is partial because legacy binary layouts and encodings need additional
  profile-specific handling.
- JPEG2000 support depends on the capabilities of the installed Pillow build.
- ANSI/NIST versions and agency profiles vary. Unknown records and fields are retained or
  reported as warnings where practical.
- Slaps, palms, latents, combined captures, unknown position codes, and duplicate records
  are displayed as Reference Record versus Comparison Record rows. Missing-position records remain
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
