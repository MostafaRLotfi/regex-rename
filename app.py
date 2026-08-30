"""Regex Rename — a Shiny for Python app to bulk-rename files/folders via regex.

Run with:
    shiny run --reload app.py
"""

import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from shiny import App, reactive, render, ui

# `pwd` is Unix-only; on Windows we fall back to the numeric uid for the Owner
# column. Guarded here so the app still imports/runs on the user's Windows box.
try:
    import pwd
except ImportError:  # pragma: no cover - Windows
    pwd = None

# Optional metadata columns the user can toggle on. Order here is the display
# order in the grid; keys match the row-dict fields built in plan().
EXTRA_COLUMNS = {
    "date_modified": "Date modified",
    "date_created": "Date created",
    "size": "File size",
    "extension": "Extension",
    "full_path": "Full path",
    "depth": "Depth",
    "name_length": "Name length",
    "owner": "Owner",
}
# Friendly header shown in the grid for each extra column.
EXTRA_HEADERS = {
    "date_modified": "date modified",
    "date_created": "date created",
    "size": "size",
    "extension": "extension",
    "full_path": "full path",
    "depth": "depth",
    "name_length": "name length",
    "owner": "owner",
}

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_text(
            "directory",
            "Directory",
            value="",
            placeholder="Paste a folder path, then click Scan",
            width="100%",
        ),
        ui.input_action_button("scan", "Scan directory", class_="btn-secondary"),
        ui.hr(),
        ui.input_radio_buttons(
            "target",
            "Apply to",
            choices={"files": "Files", "folders": "Folders", "both": "Both"},
            selected="files",
        ),
        ui.input_checkbox("recursive", "Include subdirectories (recursive)", value=False),
        ui.hr(),
        ui.input_text("pattern", "Regex pattern", value="", placeholder=r"(\d+)", width="100%"),
        ui.input_text("replacement", "Replacement", value="", placeholder=r"num_\1", width="100%"),
        ui.input_checkbox("ignore_case", "Case-insensitive", value=False),
        ui.input_checkbox(
            "ext_stem_only",
            "Files: match name only (keep extension)",
            value=True,
        ),
        ui.hr(),
        ui.popover(
            ui.input_action_button(
                "extra_cols_btn",
                "Extra columns ▾",
                class_="btn-outline-secondary",
                width="100%",
            ),
            ui.input_checkbox_group(
                "extra_cols",
                None,
                choices=EXTRA_COLUMNS,
                selected=[],  # all off by default
            ),
            title="Show extra columns",
            placement="right",
        ),
        ui.hr(),
        ui.input_action_button("apply", "Confirm & apply changes", class_="btn-danger"),
        width=340,
    ),
    ui.output_ui("status"),
    ui.input_text(
        "search",
        None,
        placeholder="Search names…",
        width="100%",
    ),
    ui.output_data_frame("preview"),
    title="Regex Rename",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def human_size(n: int) -> str:
    """Human-readable byte count, e.g. 47 KB."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1024 or unit == "PB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def fmt_time(ts: float) -> str:
    """Format a POSIX timestamp as a compact local datetime."""
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return "—"


# Whole-row background/text colors by outcome. "will rename" rows go green,
# any problem/error status goes red; "unchanged" rows are left unstyled so the
# colored rows stand out.
ROW_WILL_RENAME = {"background-color": "#d1e7dd", "color": "#0f5132"}  # green
ROW_PROBLEM = {"background-color": "#f8d7da", "color": "#842029"}  # red


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
def server(input, output, session):
    # Trigger to force a rescan after applying changes.
    apply_done = reactive.value(0)

    @reactive.calc
    def scan_base() -> Path:
        """The scanned base directory (read via isolate so typing doesn't rescan)."""
        with reactive.isolate():
            return Path(input.directory().strip().strip('"'))

    @reactive.calc
    def entries():
        """Collect the paths under the directory per settings.

        Returns "unscanned" before the first Scan, None for an invalid
        directory, or a list[Path] otherwise.
        """
        # Re-run when Scan is pressed, after an apply, or when the target/
        # recursive options change. The directory text is read via isolate so
        # typing a path doesn't rescan until Scan is clicked.
        scanned = input.scan()
        apply_done()
        target = input.target()

        if scanned == 0:
            return "unscanned"

        base = scan_base()
        if not base.is_dir():
            return None  # signal "invalid directory"

        want_files = target in ("files", "both")
        want_folders = target in ("folders", "both")

        items: list[Path] = []
        if input.recursive():
            for root, dirs, files in os.walk(base):
                root_p = Path(root)
                if want_folders:
                    items.extend(root_p / d for d in dirs)
                if want_files:
                    items.extend(root_p / f for f in files)
        else:
            try:
                children = list(base.iterdir())
            except OSError:
                return None
            for child in children:
                # A single broken symlink / permission error must not blank the
                # whole listing, so guard each stat call individually.
                try:
                    is_dir = child.is_dir()
                except OSError:
                    is_dir = False
                if is_dir:
                    if want_folders:
                        items.append(child)
                elif want_files:
                    items.append(child)
        return items

    def compute_new_name(name: str, is_dir: bool) -> str:
        """Apply the regex to a single name; return the new name."""
        pattern = input.pattern()
        replacement = input.replacement()
        flags = re.IGNORECASE if input.ignore_case() else 0

        if not is_dir and input.ext_stem_only():
            stem, ext = os.path.splitext(name)
            return re.sub(pattern, replacement, stem, flags=flags) + ext
        return re.sub(pattern, replacement, name, flags=flags)

    def norm(path: Path) -> str:
        """Normalized, case-folded absolute path for collision comparison.

        Uses abspath+normcase (never touches the filesystem) so it can't raise
        on odd/broken entries the way Path.resolve() can on Windows.
        """
        return os.path.normcase(os.path.abspath(str(path)))

    def metadata(p: Path, is_dir: bool, base: Path) -> dict:
        """Gather the optional metadata columns for one path.

        A single stat() per item, guarded so a broken entry can't blank the
        grid (mirrors the per-entry guards in entries()).
        """
        try:
            st = p.stat()
        except OSError:
            st = None

        if st is None:
            size = "—"
            date_modified = date_created = "—"
            owner = "—"
        else:
            size = "—" if is_dir else human_size(st.st_size)
            date_modified = fmt_time(st.st_mtime)
            # macOS exposes true creation time as st_birthtime; Windows uses
            # st_ctime for creation. Linux usually has neither, so fall back.
            date_created = fmt_time(getattr(st, "st_birthtime", st.st_ctime))
            if pwd is not None:
                try:
                    owner = pwd.getpwuid(st.st_uid).pw_name
                except (KeyError, OSError):
                    owner = str(st.st_uid)
            else:  # Windows
                owner = str(getattr(st, "st_uid", "—"))

        try:
            depth = len(p.relative_to(base).parts) - 1
        except ValueError:
            depth = 0

        return {
            "date_modified": date_modified,
            "date_created": date_created,
            "size": size,
            "extension": p.suffix,
            "full_path": os.path.abspath(str(p)),
            "depth": depth,
            "name_length": len(p.name),
            "owner": owner,
        }

    @reactive.calc
    def plan():
        """Build the row list: metadata always, plus rename status when a
        pattern is present. Returns None when the directory isn't a valid,
        scanned listing; otherwise a list of row dicts.
        """
        items = entries()
        if not isinstance(items, list):
            return None

        base = scan_base()
        has_pattern = bool(input.pattern())

        # First pass: is_dir + metadata + (proposed name when a pattern is set).
        computed = []
        for p in items:
            try:
                is_dir = p.is_dir()
            except OSError:
                is_dir = False
            meta = metadata(p, is_dir, base)
            if not has_pattern:
                computed.append((p, is_dir, meta, None, None))
                continue
            try:
                new_name = compute_new_name(p.name, is_dir)
            except re.error as e:
                computed.append((p, is_dir, meta, None, f"regex error: {e}"))
                continue
            computed.append((p, is_dir, meta, new_name, None))

        # Track target paths to detect collisions among the renames themselves.
        new_paths: dict[str, int] = {}
        if has_pattern:
            for p, is_dir, meta, new_name, err in computed:
                if new_name is not None:
                    np = norm(p.parent / new_name)
                    new_paths[np] = new_paths.get(np, 0) + 1

        rows = []
        for p, is_dir, meta, new_name, err in computed:
            kind = "folder" if is_dir else "file"
            if not has_pattern:
                status, changed = "", False
            elif err is not None:
                status, changed = err, False
            elif new_name == p.name:
                status, changed = "unchanged", False
            elif new_name.strip() == "" or new_name in (".", ".."):
                status, changed = "invalid name", False
            elif any(sep in new_name for sep in ("/", "\\")):
                status, changed = "invalid: contains path separator", False
            else:
                target_path = p.parent / new_name
                np = norm(target_path)
                try:
                    exists = target_path.exists()
                except OSError:
                    exists = False
                if new_paths.get(np, 0) > 1:
                    status, changed = "collision (duplicate target)", False
                elif exists and np != norm(p):
                    status, changed = "conflict (target exists)", False
                else:
                    status, changed = "will rename", True

            row = {
                "type": "📁" if is_dir else "📄",
                "old name": p.name,
                "new name": new_name if new_name is not None else "",
                "status": status,
                "_path": str(p),
                "_changed": changed,
            }
            row.update(meta)
            rows.append(row)
        return rows

    @render.ui
    def status():
        items = entries()
        if items == "unscanned":
            return ui.p(
                "Enter a directory path and click Scan directory.",
                class_="text-muted",
            )
        if items is None:
            shown = input.directory().strip().strip('"')
            return ui.div(
                ui.tags.b("Invalid directory: "),
                ui.tags.code(shown) if shown else ui.tags.i("(empty)"),
                class_="alert alert-warning",
            )
        rows = plan() or []
        if not input.pattern():
            return ui.p(
                f"{len(items)} item(s) found. Enter a regex pattern to preview renames.",
                class_="text-muted",
            )
        n_change = sum(1 for r in rows if r["_changed"])
        n_problem = sum(
            1 for r in rows if r["status"] not in ("will rename", "unchanged")
        )
        cls = "alert alert-info" if n_change else "alert alert-secondary"
        msg = f"{n_change} will be renamed"
        if n_problem:
            msg += f" · {n_problem} problem(s) — those are skipped"
        return ui.div(ui.tags.b(msg), class_=cls)

    @render.data_frame
    def preview():
        rows = plan()
        has_pattern = bool(input.pattern())

        # Column order: type icon, names, status, then the checked extras.
        base_cols = ["type", "old name", "after regex", "status"]
        extra = [k for k in EXTRA_COLUMNS if k in (input.extra_cols() or ())]
        display_cols = base_cols + [EXTRA_HEADERS[k] for k in extra]

        if not isinstance(rows, list) or not rows:
            # Nothing scanned yet, invalid dir, or no items — empty grid with the
            # column headers so the layout stays stable.
            return render.DataGrid(pd.DataFrame({c: [] for c in display_cols}))

        # Global search: substring match against current or proposed name.
        term = input.search().strip().lower()
        if term:
            rows = [
                r
                for r in rows
                if term in r["old name"].lower() or term in r["new name"].lower()
            ]

        # Default sort: colored rows float to the top — green (will rename)
        # first, then red (problem/error) — with plain "unchanged" rows below,
        # each group sorted by name. (Clicking any header re-sorts natively.)
        def _rank(r: dict) -> int:
            if r["_changed"]:  # green
                return 0
            if r["status"] not in ("", "unchanged"):  # red (problem/error)
                return 1
            return 2  # unchanged / no pattern yet

        rows = sorted(rows, key=lambda r: (_rank(r), r["old name"].lower()))

        if not rows:
            return render.DataGrid(pd.DataFrame({c: [] for c in display_cols}))

        records = []
        for r in rows:
            rec = {
                "type": r["type"],
                "old name": r["old name"],
                "after regex": r["new name"],
                "status": r["status"],
            }
            for k in extra:
                rec[EXTRA_HEADERS[k]] = r[k]
            records.append(rec)
        df = pd.DataFrame(records, columns=display_cols)

        # Whole-row coloring by status: green when it will rename, red on any
        # problem/error. Omitting "cols" applies the style across all columns.
        styles = []
        if has_pattern:
            for i, r in enumerate(rows):
                st = r["status"]
                if st in ("", "unchanged"):
                    continue
                row_style = ROW_WILL_RENAME if st == "will rename" else ROW_PROBLEM
                styles.append({"rows": [i], "style": dict(row_style)})

        return render.DataGrid(
            df,
            width="100%",
            height="70vh",
            styles=styles,
        )

    @reactive.effect
    @reactive.event(input.apply)
    def _apply():
        rows = plan()
        if not rows:
            ui.notification_show("Nothing to do.", type="warning")
            return

        to_do = [r for r in rows if r["_changed"]]
        if not to_do:
            ui.notification_show("No valid renames to apply.", type="warning")
            return

        # Rename deepest paths first so renaming a parent folder doesn't
        # invalidate the stored child paths.
        to_do.sort(key=lambda r: r["_path"].count(os.sep), reverse=True)

        ok, failed = 0, 0
        errors = []
        for r in to_do:
            src = Path(r["_path"])
            dst = src.parent / r["new name"]
            try:
                src.rename(dst)
                ok += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                errors.append(f"{src.name}: {e}")

        msg = f"Renamed {ok} item(s)."
        if failed:
            msg += f" {failed} failed."
        ui.notification_show(
            msg,
            # Failures stay until dismissed; a clean success fades on its own.
            type="warning" if failed else "message",
            duration=None if failed else 6,
            close_button=True,
        )
        for err in errors:
            ui.notification_show(
                err,
                type="error",
                duration=None,  # persist until the user clicks the X
                close_button=True,
            )
        # Refresh the listing/preview.
        apply_done.set(apply_done() + 1)


app = App(app_ui, server)
