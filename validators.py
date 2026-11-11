"""
validators.py
-------------
Checks an uploaded file *before* it is analysed, and the DataFrame after it is read.

Two stages:
  1. validate_upload(path)      -> is this a real, reasonably sized CSV / Excel file?
  2. validate_dataframe(df)     -> does the parsed table look like usable data?

Both return a ValidationResult with `errors` (stop) and `warnings` (continue).
Call `.raise_if_invalid()` to turn errors into a ValidationError.

Why check file contents and not just the extension? A renamed .exe, a PDF saved
as .csv, or a password-protected workbook all have a "valid" extension but
fail in confusing ways later on.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls"}
TEXT_EXTENSIONS = {".csv", ".tsv", ".txt"}
OPENXML_EXTENSIONS = {".xlsx", ".xlsm"}

MAX_FILE_MB = 25
MAX_UNZIPPED_MB = 300          # guards against zip bombs disguised as .xlsx
MAX_ROWS = 500_000
MAX_COLUMNS = 200
SMALL_DATASET_ROWS = 10

ZIP_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # legacy .xls, also password-protected .xlsx
OTHER_MAGIC = {
    b"%PDF": "a PDF",
    b"MZ": "an executable",
    b"\x7fELF": "an executable",
    b"\x89PNG": "an image",
    b"\xff\xd8\xff": "an image",
    b"GIF8": "an image",
}


class ValidationError(ValueError):
    """Raised when a dataset fails validation. `.errors` holds every message."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    resolved_sheet: str | int | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        if other.resolved_sheet is not None:
            self.resolved_sheet = other.resolved_sheet
        return self

    def raise_if_invalid(self) -> "ValidationResult":
        if self.errors:
            raise ValidationError(self.errors)
        return self


# --------------------------------------------------------------------------- #
# Filenames (for web uploads, where the name comes from the client)
# --------------------------------------------------------------------------- #
def safe_filename(name: str) -> str:
    """Strip directories and unusual characters from a client-supplied filename."""
    base = Path(str(name).replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return base or "upload"


# --------------------------------------------------------------------------- #
# Stage 1: the file itself
# --------------------------------------------------------------------------- #
def _read_head(path: Path, n: int = 65536) -> bytes:
    with path.open("rb") as fh:
        return fh.read(n)


def _check_text_file(head: bytes, ext: str, res: ValidationResult) -> None:
    for magic, label in OTHER_MAGIC.items():
        if head.startswith(magic):
            res.errors.append(f"The file is named {ext} but its contents look like {label}.")
            return
    if head.startswith(ZIP_MAGIC) or head.startswith(OLE_MAGIC):
        res.errors.append(
            f"The file is named {ext} but looks like an Excel workbook. Rename it to .xlsx or .xls."
        )
        return
    if b"\x00" in head:
        res.errors.append("The file contains binary data and cannot be read as text.")
        return
    try:
        head.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        # A multi-byte character may simply be cut off at the end of our 64 KB sample
        if exc.start < len(head) - 4:
            res.warnings.append("The file is not UTF-8. It will be read as Latin-1, so some characters may look wrong.")


def _check_openxml(path: Path, head: bytes, ext: str, res: ValidationResult) -> None:
    if head.startswith(OLE_MAGIC):
        res.errors.append("This workbook looks password-protected. Remove the password and upload it again.")
        return
    if not head.startswith(ZIP_MAGIC) or not zipfile.is_zipfile(path):
        res.errors.append(f"The file is named {ext} but is not a valid Excel workbook.")
        return
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            unzipped = sum(i.file_size for i in zf.infolist())
    except zipfile.BadZipFile:
        res.errors.append("The workbook is corrupted and could not be opened.")
        return
    if "xl/workbook.xml" not in names:
        res.errors.append("The file is a zip archive but not an Excel workbook.")
    elif unzipped > MAX_UNZIPPED_MB * 1024 * 1024:
        res.errors.append(f"The workbook expands to more than {MAX_UNZIPPED_MB} MB, which is too large.")


def resolve_excel_sheet(names: list[str], sheet_name: str | int | None = 0) -> tuple[str | int, str | None]:
    """
    Intelligently resolve and sanitize a user-specified sheet name or index against
    available sheet names in an Excel workbook.

    Handles:
      - None, empty string, '0', 'default', 'first' -> returns first sheet (index 0)
      - Integer index (e.g. 0, 1) and string digits (e.g. "0", "1")
      - Enclosing brackets and quotes (e.g. "[Form responses 1]" or "'Sheet1'")
      - Case-insensitive matching and whitespace normalization
      - Substring / fuzzy prefix match (e.g. "Form" -> "Form responses 1")
      - Single-sheet fallback (if workbook has only 1 sheet, automatically uses it)

    Returns (resolved_sheet, error_message_or_None).
    """
    if not names:
        return 0, "The workbook has no sheets."

    # If workbook only has 1 sheet, always resolve to that single sheet
    if len(names) == 1:
        return names[0], None

    if sheet_name is None:
        return names[0], None

    # Handle numeric integer index
    if isinstance(sheet_name, int):
        if 0 <= sheet_name < len(names):
            return names[sheet_name], None
        return sheet_name, f"Sheet index {sheet_name} does not exist. Available sheets: {names}."

    # String processing
    raw_str = str(sheet_name).strip()
    if not raw_str or raw_str.lower() in ("0", "first", "default", "auto", "none"):
        return names[0], None

    # Exact match before stripping
    if raw_str in names:
        return raw_str, None

    # Check if user entered digit string like "0" or "1"
    if raw_str.isdigit():
        idx = int(raw_str)
        if 0 <= idx < len(names):
            return names[idx], None
        if 1 <= idx <= len(names):
            return names[idx - 1], None

    # Strip surrounding brackets, quotes, braces (e.g. '[Form responses 1]' -> 'Form responses 1')
    clean = re.sub(r"^[\['\"`(\s]+|['\"`)\s\]]+$", "", raw_str).strip()
    if not clean:
        return names[0], None

    if clean in names:
        return clean, None

    # Case-insensitive & normalized whitespace match
    clean_norm = re.sub(r"\s+", " ", clean).lower()
    for name in names:
        if re.sub(r"\s+", " ", name).lower() == clean_norm:
            return name, None

    # Substring match (e.g. user typed "Form" or "responses")
    substring_matches = [name for name in names if clean_norm in re.sub(r"\s+", " ", name).lower()]
    if len(substring_matches) == 1:
        return substring_matches[0], None

    # Prefix match
    prefix_matches = [name for name in names if re.sub(r"\s+", " ", name).lower().startswith(clean_norm)]
    if len(prefix_matches) == 1:
        return prefix_matches[0], None

    formatted_available = ", ".join(f"'{n}'" for n in names)
    return sheet_name, f"Sheet '{sheet_name}' was not found. Available sheets: [{formatted_available}]."


def _check_sheet(path: Path, sheet_name: str | int, res: ValidationResult) -> None:
    try:
        names = pd.ExcelFile(path).sheet_names
    except ImportError as exc:
        res.errors.append(f"Reading Excel files needs an extra package: {exc}")
        return
    except Exception as exc:  # corrupted, protected, unsupported...
        res.errors.append(f"The workbook could not be opened ({type(exc).__name__}).")
        return

    resolved, err = resolve_excel_sheet(names, sheet_name)
    if err:
        res.errors.append(err)
        return

    res.resolved_sheet = resolved

    if len(names) > 1:
        # If user explicitly chose a sheet or workbook has multiple, inform which sheet is analyzed
        if str(sheet_name) not in ("0", ""):
            res.warnings.append(f"The workbook has {len(names)} sheets. Analysing sheet '{resolved}'.")


def validate_upload(
    path: str | Path,
    sheet_name: str | int = 0,
    max_file_mb: float = MAX_FILE_MB,
) -> ValidationResult:
    """Check that `path` is a safe, readable CSV/TSV/Excel file."""
    res = ValidationResult()
    path = Path(path)

    if not path.exists():
        res.errors.append(f"File not found: {path}")
        return res
    if not path.is_file():
        res.errors.append(f"{path} is not a file.")
        return res

    ext = path.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        res.errors.append(
            f"Unsupported file type '{ext or '(none)'}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )
        return res

    size = path.stat().st_size
    if size == 0:
        res.errors.append("The file is empty.")
        return res
    if size > max_file_mb * 1024 * 1024:
        res.errors.append(f"The file is {size / 1024 / 1024:.1f} MB. The limit is {max_file_mb:g} MB.")
        return res

    try:
        head = _read_head(path)
    except OSError as exc:
        res.errors.append(f"The file could not be read ({exc.strerror or type(exc).__name__}).")
        return res

    if ext in TEXT_EXTENSIONS:
        _check_text_file(head, ext, res)
    elif ext in OPENXML_EXTENSIONS:
        _check_openxml(path, head, ext, res)
    elif ext == ".xls" and not head.startswith(OLE_MAGIC):
        res.errors.append("The file is named .xls but is not a valid legacy Excel workbook.")

    if res.ok and ext not in TEXT_EXTENSIONS:
        _check_sheet(path, sheet_name, res)

    return res


# --------------------------------------------------------------------------- #
# Stage 2: the parsed table
# --------------------------------------------------------------------------- #
def validate_dataframe(df: pd.DataFrame) -> ValidationResult:
    """Check that a loaded DataFrame is worth analysing."""
    res = ValidationResult()

    if df.shape[1] == 0 or df.shape[0] == 0:
        res.errors.append("The file has no data rows.")
        return res
    if df.isna().all().all():
        res.errors.append("Every cell in the file is empty.")
        return res
    if df.shape[0] > MAX_ROWS:
        res.errors.append(f"The file has {df.shape[0]:,} rows. The limit is {MAX_ROWS:,}.")
    if df.shape[1] > MAX_COLUMNS:
        res.errors.append(f"The file has {df.shape[1]} columns. The limit is {MAX_COLUMNS}.")

    if df.shape[1] == 1:
        res.warnings.append(
            "Only one column was found. If you expected more, the file may use an unusual delimiter."
        )
    unnamed = sum(str(c).startswith("Unnamed:") for c in df.columns)
    if unnamed and unnamed >= df.shape[1] / 2:
        res.warnings.append("Many columns have no header. The first row may not be a header row.")
    if 0 < df.shape[0] < SMALL_DATASET_ROWS:
        res.warnings.append(f"Only {df.shape[0]} row(s) found. Statistics from so few rows are not reliable.")

    return res
