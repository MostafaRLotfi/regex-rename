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
# Skins
# ---------------------------------------------------------------------------
# Each skin sets the Bootstrap color mode ("light"/"dark") plus a textured
# palette. "Classic" skins are the plain Bootstrap themes (no texture). The
# per-skin "good"/"bad" colors drive the will-rename / problem row highlights.
# ``tex`` holds CSS background-image layers (gradients / inline-SVG noise).
SKINS: dict[str, dict] = {
    # --- Light ---
    "classic_light": {
        "label": "Classic Light", "mode": "light", "tex": None,
        "good_bg": "#d1e7dd", "good_ink": "#0f5132",
        "bad_bg": "#f8d7da", "bad_ink": "#842029",
    },
    "linen": {
        "label": "Linen", "mode": "light",
        "bg": "#ece6dc", "ink": "#3d4a44", "panel": "rgba(255,255,255,.4)",
        "field": "rgba(255,255,255,.6)", "line": "rgba(60,74,68,.22)",
        "accent": "#4a8f83", "btntext": "#ffffff",
        "good_bg": "rgba(45,130,90,.20)", "good_ink": "#20624a",
        "bad_bg": "rgba(190,70,60,.16)", "bad_ink": "#8f2f28",
        "tex": ("repeating-linear-gradient(0deg,rgba(0,0,0,.035) 0 1px,transparent 1px 4px),"
                "repeating-linear-gradient(90deg,rgba(0,0,0,.035) 0 1px,transparent 1px 4px)"),
    },
    "canvas": {
        "label": "Natural Canvas", "mode": "light",
        "bg": "#e7e0d1", "ink": "#40382c", "panel": "rgba(255,255,255,.4)",
        "field": "rgba(255,253,247,.6)", "line": "rgba(64,56,44,.22)",
        "accent": "#b5623a", "btntext": "#fff6ee",
        "good_bg": "rgba(70,120,60,.20)", "good_ink": "#33501f",
        "bad_bg": "rgba(170,70,50,.18)", "bad_ink": "#7c2f1c",
        "tex": ("repeating-linear-gradient(0deg,rgba(0,0,0,.04) 0 1px,transparent 1px 4px),"
                "repeating-linear-gradient(90deg,rgba(0,0,0,.04) 0 1px,transparent 1px 4px)"),
    },
    "cyanotype": {
        "label": "Cyanotype", "mode": "light",
        "bg": "#dde9ef", "ink": "#143a52", "panel": "rgba(255,255,255,.45)",
        "field": "rgba(255,255,255,.6)", "line": "rgba(20,90,120,.28)",
        "accent": "#1c86b0", "btntext": "#ffffff",
        "good_bg": "rgba(25,120,90,.16)", "good_ink": "#12603f",
        "bad_bg": "rgba(200,60,60,.14)", "bad_ink": "#8f2f28",
        "tex": ("repeating-linear-gradient(0deg,rgba(20,120,160,.15) 0 1px,transparent 1px 12px),"
                "repeating-linear-gradient(90deg,rgba(20,120,160,.15) 0 1px,transparent 1px 12px)"),
    },
    # --- Dark ---
    "classic_dark": {
        "label": "Classic Dark", "mode": "dark", "tex": None,
        "good_bg": "#d1e7dd", "good_ink": "#0f5132",
        "bad_bg": "#f8d7da", "bad_ink": "#842029",
    },
    "carbon": {
        "label": "Slate Carbon", "mode": "dark",
        "bg": "#22272c", "ink": "#e6edf3", "panel": "rgba(255,255,255,.03)",
        "field": "rgba(255,255,255,.05)", "line": "rgba(255,255,255,.10)",
        "accent": "#4dd0e1", "btntext": "#04222a",
        "good_bg": "rgba(77,208,118,.20)", "good_ink": "#9be8b6",
        "bad_bg": "rgba(255,107,107,.20)", "bad_ink": "#ffb1b1",
        "tex": ("repeating-linear-gradient(45deg,rgba(255,255,255,.035) 0 1px,transparent 1px 3px),"
                "repeating-linear-gradient(-45deg,rgba(0,0,0,.25) 0 1px,transparent 1px 3px)"),
    },
    "graphite": {
        "label": "Graphite Mesh", "mode": "dark",
        "bg": "#26292e", "ink": "#e9ebef", "panel": "rgba(255,255,255,.04)",
        "field": "rgba(255,255,255,.05)", "line": "rgba(255,255,255,.11)",
        "accent": "#f2b544", "btntext": "#2a2010",
        "good_bg": "rgba(120,210,130,.20)", "good_ink": "#a8e6b4",
        "bad_bg": "rgba(255,120,110,.20)", "bad_ink": "#ffb8b0",
        "tex": ("radial-gradient(rgba(255,255,255,.08) 1px,transparent 1.6px) 0 0/13px 13px,"
                "repeating-linear-gradient(0deg,rgba(0,0,0,.14) 0 1px,transparent 1px 13px)"),
    },
    "gunmetal": {
        "label": "Gunmetal", "mode": "dark",
        "bg": "#2b2f34", "ink": "#eceff2", "panel": "rgba(255,255,255,.04)",
        "field": "rgba(255,255,255,.06)", "line": "rgba(255,255,255,.12)",
        "accent": "#86a5c4", "btntext": "#0e1a26",
        "good_bg": "rgba(90,200,140,.20)", "good_ink": "#a6e6c2",
        "bad_bg": "rgba(255,120,120,.20)", "bad_ink": "#ffbdbd",
        "tex": ("linear-gradient(90deg,rgba(255,255,255,.06),transparent 45%,rgba(255,255,255,.05)),"
                "repeating-linear-gradient(0deg,rgba(255,255,255,.05) 0 1px,rgba(0,0,0,.06) 1px 2px)"),
    },
    "blueprint": {
        "label": "Blueprint", "mode": "dark",
        "bg": "#0e3a5f", "ink": "#eaf3fb", "panel": "rgba(255,255,255,.05)",
        "field": "rgba(255,255,255,.08)", "line": "rgba(255,255,255,.20)",
        "accent": "#7fd0ff", "btntext": "#0e3a5f",
        "good_bg": "rgba(120,230,160,.18)", "good_ink": "#bff2d2",
        "bad_bg": "rgba(255,130,130,.20)", "bad_ink": "#ffc2c2",
        "tex": ("repeating-linear-gradient(0deg,rgba(255,255,255,.10) 0 1px,transparent 1px 13px),"
                "repeating-linear-gradient(90deg,rgba(255,255,255,.10) 0 1px,transparent 1px 13px)"),
    },
    "circuit": {
        "label": "Circuit Navy", "mode": "dark",
        "bg": "#10233a", "ink": "#dbeafc", "panel": "rgba(120,200,255,.05)",
        "field": "rgba(255,255,255,.06)", "line": "rgba(120,200,255,.20)",
        "accent": "#6cc6ff", "btntext": "#0b1b2e",
        "good_bg": "rgba(120,230,160,.18)", "good_ink": "#bff2d2",
        "bad_bg": "rgba(255,130,130,.20)", "bad_ink": "#ffc2c2",
        "tex": ("repeating-linear-gradient(0deg,rgba(120,200,255,.13) 0 1px,transparent 1px 13px),"
                "repeating-linear-gradient(90deg,rgba(120,200,255,.13) 0 1px,transparent 1px 13px)"),
    },
    "denim": {
        "label": "Denim", "mode": "dark",
        "bg": "#3f5a78", "ink": "#eef3f8", "panel": "rgba(255,255,255,.06)",
        "field": "rgba(255,255,255,.10)", "line": "rgba(255,255,255,.18)",
        "accent": "#e8d9b5", "btntext": "#33465e",
        "good_bg": "rgba(130,225,165,.22)", "good_ink": "#d6f3e0",
        "bad_bg": "rgba(255,145,140,.22)", "bad_ink": "#ffcccc",
        "tex": ("repeating-linear-gradient(45deg,rgba(255,255,255,.05) 0 1px,transparent 1px 3px),"
                "repeating-linear-gradient(-45deg,rgba(0,0,0,.14) 0 1px,transparent 1px 3px)"),
    },
}

# Grouped choices for the Settings dropdown (optgroups keep light/dark apart).
SKIN_CHOICES = {
    "Light": {k: v["label"] for k, v in SKINS.items() if v["mode"] == "light"},
    "Dark": {k: v["label"] for k, v in SKINS.items() if v["mode"] == "dark"},
}
DEFAULT_SKIN = "classic_light"


def build_skin_css(skin: dict) -> str:
    """CSS that paints the app's chrome for a textured skin.

    Classic skins return "" and rely on Bootstrap's own light/dark theme; the
    data grid and form controls follow ``data-bs-theme`` (set client-side).
    """
    if not skin.get("tex"):
        return ""
    return f"""
    body {{ background-color:{skin['bg']}; background-image:{skin['tex']};
            background-attachment:fixed; color:{skin['ink']}; }}
    .navbar {{ background-color:{skin['panel']} !important;
               border-bottom:1px solid {skin['line']}; }}
    .navbar .navbar-brand, .navbar .nav-link, .navbar .nav-link.active {{
        color:{skin['ink']} !important; }}
    .bslib-sidebar-layout>.sidebar {{ background-color:{skin['panel']};
        border-color:{skin['line']}; }}
    .bslib-sidebar-layout>.main {{ background-color:transparent; }}
    .card, .bslib-card, .modal-content, .popover, .popover-body {{
        background-color:{skin['bg']}; color:{skin['ink']}; }}
    .form-control, .form-select {{ background-color:{skin['field']};
        color:{skin['ink']}; border-color:{skin['line']}; }}
    .btn-secondary {{ background-color:{skin['accent']};
        border-color:{skin['accent']}; color:{skin['btntext']}; }}
    .btn-outline-secondary {{ color:{skin['ink']}; border-color:{skin['line']}; }}
    .nav-tabs .nav-link.active, .nav-underline .nav-link.active {{
        color:{skin['ink']}; }}
    """


# JS: apply a skin sent from the server (set the Bootstrap color mode and swap
# a <style> element). Polls until Shiny is ready so registration can't race.
_SKIN_JS = """
(function reg(){
  if(!window.Shiny || !Shiny.addCustomMessageHandler){ return setTimeout(reg,50); }
  Shiny.addCustomMessageHandler('apply-skin', function(m){
    document.documentElement.setAttribute('data-bs-theme', m.mode);
    var el = document.getElementById('app-skin');
    if(!el){ el = document.createElement('style'); el.id = 'app-skin';
             document.head.appendChild(el); }
    el.textContent = m.css;
  });
})();
"""

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
app_ui = ui.page_navbar(
    ui.nav_panel(
        "Rename",
        ui.layout_sidebar(
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
        ui.input_action_button(
            "cheatsheet",
            "📖 Regex cheat sheet",
            class_="btn-link btn-sm p-0",
        ),
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
        ),
    ),
    ui.nav_panel(
        "Settings",
        ui.h4("Appearance", class_="mt-2"),
        ui.input_select(
            "skin",
            "Skin",
            choices=SKIN_CHOICES,
            selected=DEFAULT_SKIN,
            width="320px",
        ),
        ui.help_text(
            "Light and dark skins are grouped separately. Textured skins are "
            "pure CSS — no image files."
        ),
    ),
    title="Regex Rename",
    id="nav",
    header=ui.tags.script(ui.HTML(_SKIN_JS)),
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



# Quick-reference regex content shown in the cheat-sheet modal. Each section is
# (heading, [(token, meaning, example), ...]); token and example render in
# <code> cells.
CHEATSHEET = [
    (
        "Character classes",
        [
            (".", "any character except newline", 'a.c → "abc"'),
            (r"\d", "a digit (0–9)", r'\d\d → "42"'),
            (r"\D", "a non-digit", r'\D → "x" in "x9"'),
            (r"\w", "a word char (letter, digit, _)", r'\w+ → "file_1"'),
            (r"\W", "a non-word char", r'\W → "-" in "a-b"'),
            (r"\s", "whitespace (space, tab, …)", r'a\sb → "a b"'),
            (r"\S", "non-whitespace", r'\S+ → "hello"'),
        ],
    ),
    (
        "Sets & groups",
        [
            ("[abc]", "any one of a, b, or c", '[aeiou] → "e"'),
            ("[^abc]", "any char except a, b, c", '[^0-9] → "x"'),
            ("[a-z]", "any char in the range a–z", '[a-f] → "c"'),
            ("(...)", r"capturing group → use as \1 in Replacement", r'(\d+) captures "0001"'),
            ("(?:...)", "group without capturing", '(?:ab)+ → "abab"'),
            ("a|b", "match a or b", 'jpg|png → "png"'),
        ],
    ),
    (
        "Anchors & quantifiers",
        [
            ("^", "start of the name", '^IMG → "IMG…"'),
            ("$", "end of the name", r'\.txt$ → "….txt"'),
            (r"\b", "word boundary", r'\bfile\b → whole word "file"'),
            ("*", "0 or more of the previous", 'ab* → "a", "abbb"'),
            ("+", "1 or more of the previous", r'\d+ → "12"'),
            ("?", "0 or 1 (makes it optional)", 'colou?r → "color"/"colour"'),
            ("{n}", "exactly n", r'\d{4} → "2024"'),
            ("{n,m}", "between n and m", r'\d{2,4} → "12"–"1234"'),
            ("+? / *?", "lazy: as few as possible", ".+? → shortest match"),
        ],
    ),
    (
        "Escaping & replacement",
        [
            (r"\.", r"a literal dot (escape . ^ $ * + ? ( ) [ ] { } | \ )", r'\.jpg → ".jpg"'),
            (r"\1 \2", "insert captured group 1, 2 in Replacement", r"(\w+)-(\d+) → \2_\1"),
            (r"\g<1>", r"same as \1 (use before a literal digit)", r"…\g<1>0 → group, then 0"),
        ],
    ),
]

# A few rename-focused worked examples: (pattern, replacement, before → after).
CHEATSHEET_EXAMPLES = [
    (r"IMG_(\d+)", r"photo_\1", "IMG_0001 → photo_0001"),
    (r"\s+", "_", "my report → my_report"),
    (r"(\d{4})-(\d{2})-(\d{2})", r"\1_\2_\3", "2023-01-15 → 2023_01_15"),
    (r"\.txt$", ".md", "notes.txt → notes.md  (turn off name-only)"),
]


def cheatsheet_modal():
    """Build the regex cheat-sheet modal shown by the sidebar button."""

    def section(heading, entries):
        body = [
            ui.tags.tr(
                ui.tags.td(
                    ui.tags.code(tok),
                    style="white-space:nowrap;vertical-align:top;padding-right:.6rem;",
                ),
                ui.tags.td(desc, style="vertical-align:top;padding-right:.6rem;"),
                ui.tags.td(
                    ui.tags.code(ex, style="color:#6c757d;"),
                    style="vertical-align:top;",
                ),
            )
            for tok, desc, ex in entries
        ]
        return ui.div(
            ui.tags.b(heading),
            ui.tags.table(
                ui.tags.tbody(*body),
                class_="table table-sm",
                style="margin-top:.25rem;",
            ),
        )

    example_rows = [
        ui.tags.tr(
            ui.tags.td(ui.tags.code(pat), style="padding-right:.75rem;"),
            ui.tags.td(ui.tags.code(rep), style="padding-right:.75rem;"),
            ui.tags.td(ex, class_="text-muted"),
        )
        for pat, rep, ex in CHEATSHEET_EXAMPLES
    ]

    return ui.modal(
        ui.p(
            "This app uses Python's ",
            ui.tags.code("re.sub"),
            " — the Pattern is matched and the Replacement is substituted, so "
            "backreferences like ",
            ui.tags.code(r"\1"),
            " work.",
            class_="text-muted",
        ),
        ui.div(
            *[section(h, pairs) for h, pairs in CHEATSHEET],
            style="display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));"
            "gap:0 1.5rem;",
        ),
        ui.hr(),
        ui.tags.b("Examples"),
        ui.tags.table(
            ui.tags.thead(
                ui.tags.tr(
                    ui.tags.th("pattern"),
                    ui.tags.th("replacement"),
                    ui.tags.th("result"),
                )
            ),
            ui.tags.tbody(*example_rows),
            class_="table table-sm",
            style="margin-top:.25rem;",
        ),
        title="Regex cheat sheet",
        easy_close=True,
        size="l",
        footer=ui.modal_button("Close"),
    )


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
        # Only rows that actually move (new_name differs from the current name)
        # count: an unchanged file "targeting" its own name isn't a competing
        # rename, so renaming onto it is reported as a conflict, not a collision.
        new_paths: dict[str, int] = {}
        if has_pattern:
            for p, is_dir, meta, new_name, err in computed:
                if new_name is not None and new_name != p.name:
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

        # Whole-row coloring by status, using the current skin's palette: green
        # when it will rename, red on any problem/error. Omitting "cols" applies
        # the style across all columns.
        skin = SKINS.get(input.skin(), SKINS[DEFAULT_SKIN])
        good_style = {"background-color": skin["good_bg"], "color": skin["good_ink"]}
        bad_style = {"background-color": skin["bad_bg"], "color": skin["bad_ink"]}
        styles = []
        if has_pattern:
            for i, r in enumerate(rows):
                st = r["status"]
                if st in ("", "unchanged"):
                    continue
                row_style = good_style if st == "will rename" else bad_style
                styles.append({"rows": [i], "style": dict(row_style)})

        return render.DataGrid(
            df,
            width="100%",
            height="70vh",
            styles=styles,
        )

    @reactive.effect
    @reactive.event(input.cheatsheet)
    def _show_cheatsheet():
        ui.modal_show(cheatsheet_modal())

    @reactive.effect
    async def _apply_skin():
        """Push the selected skin to the client: set the Bootstrap color mode
        and swap the injected <style>. Runs on connect and on every change."""
        skin = SKINS.get(input.skin(), SKINS[DEFAULT_SKIN])
        await session.send_custom_message(
            "apply-skin",
            {"mode": skin["mode"], "css": build_skin_css(skin)},
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
