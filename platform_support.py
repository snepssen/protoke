"""Cross-platform replacements for the tool's former macOS-only calls.

Everything here degrades rather than fails: a missing file dialog toolkit
leaves the browser UI's typed-path entry as the way in, and a desktop with no
file manager still renders video.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")

AUDIO_EXTS = ("wav", "mp3", "m4a", "flac", "aiff", "aif", "ogg")
IMAGE_EXTS = ("png", "jpg", "jpeg", "webp", "tif", "tiff")
LYRIC_EXTS = ("md", "txt", "rtf")


# ------------------------------------------------------------------ binaries

def _exe(name):
    return name + ".exe" if IS_WINDOWS else name


def find_ffmpeg():
    """Prefer a build that actually carries the subtitles (libass) filter.

    Slim distribution builds omit it, and the failure only shows up as a
    cryptic filter error deep into a render, so probe for the filter itself
    rather than trusting the first ffmpeg on PATH.
    """
    candidates = []
    env = os.environ.get("LYRIC_VIDEO_FFMPEG")
    if env:
        candidates.append(env)
    if IS_MACOS:
        candidates += ["/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
                       "/usr/local/opt/ffmpeg-full/bin/ffmpeg"]
    found = shutil.which(_exe("ffmpeg"))
    if found:
        candidates.append(found)
    if IS_MACOS:
        candidates += ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]
    elif IS_LINUX:
        candidates += ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg",
                       "/snap/bin/ffmpeg"]
    elif IS_WINDOWS:
        for base in (os.environ.get("ProgramFiles", ""),
                     os.environ.get("LOCALAPPDATA", "")):
            if base:
                candidates.append(os.path.join(base, "ffmpeg", "bin",
                                               "ffmpeg.exe"))

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            result = subprocess.run(
                [candidate, "-hide_banner", "-h", "filter=subtitles"],
                capture_output=True, text=True, timeout=10,
                **_no_console())
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 \
                and "Unknown filter" not in result.stdout \
                and "Unknown filter" not in result.stderr:
            return candidate
    return None


def find_ffprobe(ffmpeg_path):
    """ffprobe from the same build as the chosen ffmpeg, else whatever's on PATH."""
    if ffmpeg_path:
        folder = os.path.dirname(ffmpeg_path)
        if folder:
            sibling = os.path.join(folder, _exe("ffprobe"))
            if os.path.isfile(sibling):
                return sibling
    return shutil.which(_exe("ffprobe")) or _exe("ffprobe")


def _no_console():
    """Keep console windows from flashing up on Windows."""
    if not IS_WINDOWS:
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {"startupinfo": startup,
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def ffmpeg_install_hint():
    if IS_MACOS:
        return "brew install ffmpeg"
    if IS_WINDOWS:
        return "winget install Gyan.FFmpeg"
    return "sudo apt install ffmpeg  (or your distribution's package)"


# ---------------------------------------------------------------- typography

def default_font():
    """A grotesque that is actually installed on this platform."""
    if IS_MACOS:
        return "SF Pro Display"
    if IS_WINDOWS:
        return "Segoe UI"
    return "DejaVu Sans"


def font_choices():
    """Suggestions for the UI's typeface list, most likely installed first."""
    shared = ["Arial Black", "Impact", "Verdana", "Georgia"]
    if IS_MACOS:
        return ["SF Pro Display", "SF Pro Rounded", "Helvetica Neue",
                "Avenir Next", "Futura", "Geneva", "Lato"] + shared
    if IS_WINDOWS:
        return ["Segoe UI", "Segoe UI Variable", "Bahnschrift", "Calibri",
                "Tahoma", "Trebuchet MS"] + shared
    return ["DejaVu Sans", "Liberation Sans", "Noto Sans", "Ubuntu",
            "Cantarell", "FreeSans"] + shared


# -------------------------------------------------------------- file dialogs

_FILTERS = {
    "audio": ("Choose audio file", "Audio", AUDIO_EXTS),
    "image": ("Choose cover art", "Images", IMAGE_EXTS),
    "lyrics": ("Choose lyric sheet", "Lyric sheets", LYRIC_EXTS),
}


class PickerUnavailable(RuntimeError):
    """No native dialog toolkit — the caller should offer typed paths."""


def pick(kind, scan_audio_tree=None):
    """Return chosen paths for 'audio', 'audioFolder', 'image', 'lyrics' or
    'folder'. Raises PickerUnavailable when no dialog toolkit is present."""
    if kind in ("audioFolder", "folder"):
        prompt = ("Choose a folder of audio files" if kind == "audioFolder"
                  else "Choose output folder")
        folder = _pick_directory(prompt)
        if not folder:
            return []
        if kind == "folder":
            return [folder]
        return scan_audio_tree(folder) if scan_audio_tree else [folder]

    prompt, label, extensions = _FILTERS.get(kind, _FILTERS["audio"])
    chosen = _pick_file(prompt, label, extensions)
    return [chosen] if chosen else []


def _pick_file(prompt, label, extensions):
    if IS_MACOS:
        types = ", ".join(f'"{ext}"' for ext in extensions)
        out = _osascript(
            f'POSIX path of (choose file with prompt "{prompt}" '
            f'of type {{{types}}})')
        if out is not None:
            return out
    return _tk_dialog("file", prompt, label, extensions)


def _pick_directory(prompt):
    if IS_MACOS:
        out = _osascript(f'POSIX path of (choose folder with prompt "{prompt}")')
        if out is not None:
            return out
    return _tk_dialog("directory", prompt, "", ())


def _osascript(script):
    """macOS native picker. Returns None when osascript itself is unusable,
    and '' when the user cancelled — the two need different fallbacks."""
    try:
        result = subprocess.run(["osascript", "-e", script],
                                capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        # -128 is the user pressing Cancel; anything else is a broken picker.
        return "" if "-128" in (result.stderr or "") else None
    return result.stdout.strip()


def _tk_dialog(mode, prompt, label, extensions):
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError as exc:
        raise PickerUnavailable(
            "No file dialog is available. Install Python's tkinter support "
            "(for example 'sudo apt install python3-tk'), or paste the file "
            "path into the field instead.") from exc

    try:
        root = tkinter.Tk()
    except tkinter.TclError as exc:
        raise PickerUnavailable(
            "No desktop session was found for a file dialog. Paste the file "
            "path into the field instead.") from exc
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        if mode == "directory":
            chosen = filedialog.askdirectory(title=prompt, parent=root)
        else:
            patterns = " ".join(f"*.{ext}" for ext in extensions)
            chosen = filedialog.askopenfilename(
                title=prompt, parent=root,
                filetypes=[(label, patterns), ("All files", "*.*")])
    finally:
        root.destroy()
    return chosen or ""


# ------------------------------------------------------------------- reveal

def reveal(path):
    """Show a finished file in the platform's file manager. Best effort."""
    if not path or not os.path.exists(path):
        return False
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    try:
        if IS_MACOS:
            subprocess.run(["open", "-R", path], timeout=20)
        elif IS_WINDOWS:
            if os.path.isdir(path):
                os.startfile(path)  # noqa: S606 - documented Windows API
            else:
                subprocess.run(["explorer", "/select,", os.path.normpath(path)],
                               timeout=20)
        else:
            opener = (shutil.which("xdg-open") or shutil.which("gio")
                      or shutil.which("nautilus"))
            if not opener:
                return False
            if opener.endswith("gio"):
                subprocess.run([opener, "open", folder], timeout=20)
            else:
                subprocess.run([opener, folder], timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True


def config_dir(name="protoke"):
    """Where the user's own settings live — kept apart from the cache.

    A cache can be deleted to reclaim disk; saved face presets cannot.
    """
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif IS_MACOS:
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = (os.environ.get("XDG_CONFIG_HOME")
                or os.path.expanduser("~/.config"))
    return os.path.join(base, name)


def cache_dir(name="protoke"):
    """Per-user cache location following each platform's convention."""
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif IS_MACOS:
        base = os.path.expanduser("~/Library/Caches")
    else:
        base = (os.environ.get("XDG_CACHE_HOME")
                or os.path.expanduser("~/.cache"))
    return os.path.join(base, name)
