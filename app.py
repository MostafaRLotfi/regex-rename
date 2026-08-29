"""Regex Rename — a Shiny for Python app to bulk-rename files/folders via regex.

Run with:
    shiny run --reload app.py
"""

import os
import re
from pathlib import Path

from shiny import App, reactive, render, ui

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_text(
            "directory",
            "Directory",
            value=str(Path.home()),
            placeholder=r"C:\Users\you\folder",
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
    ui.output_ui("preview"),
    title="Regex Rename",
)


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
def server(input, output, session):
    # Trigger to force a rescan after applying changes.
    apply_done = reactive.value(0)

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

        with reactive.isolate():
            base = Path(input.directory().strip().strip('"'))
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

    @reactive.calc
    def plan():
        """Build the rename plan: list of dicts with old/new/status."""
        items = entries()
        if not isinstance(items, list):
            return None
        if not input.pattern():
            return []

        rows = []
        # Track target paths to detect collisions among the renames themselves.
        new_paths: dict[str, int] = {}

        # First pass: compute proposed names.
        computed = []
        for p in items:
            try:
                is_dir = p.is_dir()
            except OSError:
                is_dir = False
            try:
                new_name = compute_new_name(p.name, is_dir)
            except re.error as e:
                computed.append((p, is_dir, None, f"regex error: {e}"))
                continue
            computed.append((p, is_dir, new_name, None))

        for p, is_dir, new_name, err in computed:
            if new_name is not None:
                np = norm(p.parent / new_name)
                new_paths[np] = new_paths.get(np, 0) + 1

        for p, is_dir, new_name, err in computed:
            kind = "folder" if is_dir else "file"
            if err is not None:
                status = err
                changed = False
            elif new_name == p.name:
                status = "unchanged"
                changed = False
            elif new_name.strip() == "" or new_name in (".", ".."):
                status = "invalid name"
                changed = False
            elif any(sep in new_name for sep in ("/", "\\")):
                status = "invalid: contains path separator"
                changed = False
            else:
                target_path = p.parent / new_name
                np = norm(target_path)
                try:
                    exists = target_path.exists()
                except OSError:
                    exists = False
                if new_paths.get(np, 0) > 1:
                    status = "collision (duplicate target)"
                    changed = False
                elif exists and np != norm(p):
                    status = "conflict (target exists)"
                    changed = False
                else:
                    status = "will rename"
                    changed = True

            rows.append(
                {
                    "type": kind,
                    "folder": str(p.parent),
                    "old name": p.name,
                    "new name": new_name if new_name is not None else "",
                    "status": status,
                    "_path": str(p),
                    "_changed": changed,
                }
            )
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
            return ui.div(
                ui.tags.b("Invalid directory: "),
                ui.tags.code(input.directory().strip().strip('"')),
                class_="alert alert-warning",
            )
        rows = plan()
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

    @render.ui
    def preview():
        # Plain HTML table (no pandas/numpy) to avoid the ABI mismatch and
        # keep full control over the two-column layout and row coloring.
        items = entries()
        if not isinstance(items, list):
            return ui.div()
        if not items:
            return ui.p("No matching items in this directory.", class_="text-muted")

        rows = plan()  # None/[] when no pattern; else list of dicts
        has_plan = bool(rows)

        # Case-insensitive substring filter from the search box (matches either
        # the current name or the proposed new name).
        term = input.search().strip().lower()

        def matches(current: str, after: str) -> bool:
            if not term:
                return True
            return term in current.lower() or term in after.lower()

        # Colors for the "after regex" cell based on status.
        good = {"will rename"}
        neutral = {"unchanged"}

        body = []
        total = 0
        if has_plan:
            for r in rows:
                total += 1
                after = r["new name"] or ""
                if not matches(r["old name"], after):
                    continue
                status = r["status"]
                if status in good:
                    color, weight = "#198754", "600"  # green
                elif status in neutral:
                    color, weight = "#6c757d", "400"  # grey
                else:
                    color, weight = "#dc3545", "600"  # red (problem)
                title = status if status not in neutral else ""
                body.append(
                    ui.tags.tr(
                        ui.tags.td(r["old name"]),
                        ui.tags.td(
                            after,
                            title=title,
                            style=f"color:{color};font-weight:{weight};",
                        ),
                    )
                )
        else:
            for p in items:
                total += 1
                if not matches(p.name, ""):
                    continue
                body.append(
                    ui.tags.tr(ui.tags.td(p.name), ui.tags.td(""))
                )

        if not body:
            return ui.p(
                f"No names match “{input.search().strip()}”.", class_="text-muted"
            )

        header = ui.tags.thead(
            ui.tags.tr(
                ui.tags.th("current name", style="text-align:left;"),
                ui.tags.th("after regex", style="text-align:left;"),
            )
        )
        table = ui.tags.table(
            header,
            ui.tags.tbody(*body),
            class_="table table-sm table-striped",
            style="width:100%;",
        )
        return ui.div(
            table,
            style="max-height:70vh;overflow:auto;border:1px solid #dee2e6;border-radius:.375rem;",
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
