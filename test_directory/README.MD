# Sample test directory

A throwaway set of messy filenames so you can try **Regex Rename** without
touching your own files. Point the app's **Directory** field at this folder
(use the full path, e.g. `.../regex-rename/test_directory`) and click
**Scan directory**.

Most files are empty stubs, but a couple are **real, openable content** — a
public-domain Oscar Wilde play and a sad-trombone sound clip — so renaming feels
concrete. Their licenses are in [`ATTRIBUTIONS.md`](ATTRIBUTIONS.md).

Each group below is a scenario with a regex you can paste in to see it work.
Turn on **Case-insensitive** and **Files: match name only (keep extension)**
where noted. For the nested folders, enable **Include subdirectories
(recursive)**.

## Things to try

| Files | Goal | Pattern | Replacement | Notes |
|-------|------|---------|-------------|-------|
| `IMG_0001.JPG`, `DSC00047.jpg` | Give photos a friendlier prefix | `^(IMG\|DSC)_?0*(\d+)` | `vacation_\2` | case-insensitive on |
| `2023_01_15_meeting.txt`, `2023-03-05-meeting.txt` | Normalize date separators | `(\d{4})[-_](\d{2})[-_](\d{2})` | `\1-\2-\3` | mixes `_` and `-` sources |
| `Untitled document (1).txt` | Kill spaces and parentheses | ` \((\d+)\)` | `_\1` | then try `Untitled document` → `notes` |
| `track1.mp3` … `track11.mp3` | Regex-only won't zero-pad | `track(\d)$` | `track0\1` | pad single digits (leaves `track10`,`track11`) |
| `README.MD`, `notes.TXT`, `Data.CSV` | Lowercase-looking names | `^(.*)$` | `\1` | try matching just the stem |
| `... FINAL.txt`, `final report FINAL.docx` | Strip the "FINAL" clutter | ` ?FINAL$` | *(empty)* | real Wilde play + a stub doc |
| `sad trombone SFX.ogg` | Tidy a sound clip name | ` SFX$` | `` | real playable `.ogg` audio |
| `old_project_alpha/`, `old_project_beta/` | Rename folders | `^old_project_` | `2024_` | set **Apply to → Folders** |
| `invoices/**` | Recurse into subfolders | `inv_0*(\d+)` | `invoice-\1` | enable **recursive**, **Files** |

## Resetting after you experiment

The app renames real files, so after playing around, restore the originals
from git (run from the repo root):

```bash
git checkout -- test_directory     # restore renamed/deleted tracked files
git clean -fd test_directory       # remove any new files your renames created
```
