#!/usr/bin/env python3
"""Getting the things Protoke needs, rather than complaining that they are gone.

Protoke ships neither ffmpeg nor a transcription engine. That is the right
call, but for a long time it handed the gap to the person in front of it: a
sentence saying `brew install ffmpeg`, and then nothing. Being told "install
ffmpeg" and being asked "shall I install ffmpeg?" are a different experience,
and only one of them is a tool doing its job.

So: everything missing is listed, the exact commands are shown, and the
default answer is yes to all of it. Pressing return installs everything.

**Two things it will not do.** It never invokes `sudo` on anybody's behalf —
on a distribution whose package manager needs root, the command is printed to
run by hand. And it never installs anything without being asked, except when
told `--yes`, which is there for `setup.sh` and for scripts.

ffmpeg is judged by whether the build carries the subtitles (libass) filter,
because that is what burns the lyrics in, not by whether a binary of that
name exists. Homebrew's plain `ffmpeg` no longer has it; `ffmpeg-full` does.
So "missing" and "the one you have will not do" read as different sentences.

Vocal separation (about a gigabyte of PyTorch) is the one thing not offered by
default, as `setup.sh` always had it: `--with-separation` adds it.
"""

import os
import platform
import shutil
import subprocess
import sys

import platform_support

HERE = os.path.dirname(os.path.abspath(__file__))
BANNER = "Protoke needs a few things it does not ship."

# How to install ffmpeg with subtitles, per package manager. `needs_root`
# decides whether the command is run or only printed.
MANAGERS = {
    "brew":   {"probe": "brew", "command": ["brew", "install"], "ffmpeg": "ffmpeg-full",
               "needs_root": False, "label": "Homebrew"},
    "winget": {"probe": "winget", "command": ["winget", "install", "-e", "--id"],
               "ffmpeg": "Gyan.FFmpeg", "needs_root": False, "label": "winget"},
    "apt":    {"probe": "apt-get", "command": ["sudo", "apt-get", "install", "-y"],
               "ffmpeg": "ffmpeg", "needs_root": True, "label": "apt"},
    "dnf":    {"probe": "dnf", "command": ["sudo", "dnf", "install", "-y"],
               "ffmpeg": "ffmpeg", "needs_root": True, "label": "dnf"},
    "pacman": {"probe": "pacman", "command": ["sudo", "pacman", "-S", "--noconfirm"],
               "ffmpeg": "ffmpeg", "needs_root": True, "label": "pacman"},
}


def current_manager():
    order = {"darwin": ["brew"], "win32": ["winget"]}.get(
        sys.platform, ["apt", "dnf", "pacman", "brew"])
    return next((m for m in order if shutil.which(MANAGERS[m]["probe"])), None)


def venv_python():
    folder = "Scripts" if platform_support.IS_WINDOWS else "bin"
    name = "python.exe" if platform_support.IS_WINDOWS else "python"
    return os.path.join(HERE, ".venv", folder, name)


def engine_packages(separation=False):
    """What `.venv` holds: the portable engine, the desktop window, and on
    Apple silicon the faster MLX engine. Separation only when asked."""
    packages = ["onnx-asr[cpu,hub]", "pywebview"]
    if sys.platform == "darwin" and platform.machine() == "arm64":
        packages.append("parakeet-mlx")
    if separation:
        packages += ["audio-separator[cpu]", "audioread"]
    return packages


def has_engine():
    python = venv_python()
    if not os.path.exists(python):
        return False
    probe = subprocess.run([python, "-c", "import onnx_asr"], capture_output=True)
    return probe.returncode == 0


def has_separation():
    python = venv_python()
    return os.path.exists(python) and subprocess.run(
        [python, "-c", "import audio_separator"], capture_output=True).returncode == 0


def unusable_ffmpeg():
    """An ffmpeg exists, but none with the subtitles filter."""
    return shutil.which("ffmpeg") is not None and platform_support.find_ffmpeg() is None


def survey(separation=False):
    """What is missing: ffmpeg is needed, the engine is an extra."""
    needed, extra = [], []
    if platform_support.find_ffmpeg() is None:
        needed.append(("ffmpeg", "burns the lyrics into the video (with libass)"))
    if not has_engine():
        extra.append(("engine", "transcribes the vocal so the words land on time"))
    if separation and not has_separation():
        extra.append(("separation", "isolates the voice for wordless singing (~1 GB)"))
    return {"manager": current_manager(), "required": needed, "optional": extra}


def ffmpeg_command(manager):
    spec = MANAGERS[manager]
    return spec["command"] + [spec["ffmpeg"]]


def engine_steps(separation=False):
    steps = []
    if not os.path.exists(venv_python()):
        steps.append([sys.executable, "-m", "venv", os.path.join(HERE, ".venv")])
    steps.append([venv_python(), "-m", "pip", "install", "--upgrade", "pip"])
    steps.append([venv_python(), "-m", "pip", "install", *engine_packages(separation)])
    return steps


def describe(key, manager, separation=False):
    if key == "ffmpeg":
        return " ".join(ffmpeg_command(manager)) if manager else "(no package manager found)"
    return "\n  ".join(" ".join(step) for step in engine_steps(separation))


def run(argv, on_line):
    on_line(f"$ {' '.join(argv)}")
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.SubprocessError) as error:
        return str(error)
    if done.returncode == 0:
        return None
    detail = (done.stderr or done.stdout or "").strip().splitlines()
    return detail[-1] if detail else f"exit {done.returncode}"


def install(keys, manager, separation=False, on_line=print):
    """Run the installs. Returns [(key, ok, detail)]; ok is asked of the disk."""
    results = []
    for key in keys:
        if key == "ffmpeg":
            # Ask the disk, not the exit code: Homebrew returns non-zero for
            # things that are not failures, such as already installed.
            problem = run(ffmpeg_command(manager), on_line)
            ok = platform_support.find_ffmpeg() is not None
        else:
            problem = None
            for step in engine_steps(separation):
                problem = run(step, on_line)
                if problem:
                    break
            ok = has_engine() and (not separation or has_separation())
        results.append((key, ok, "" if ok else (problem or "installed, but not found afterwards")))
    return results


def offer(assume_yes=False, quiet=False, separation=False):
    """Show what is missing and install it. True when nothing needed is left."""
    state = survey(separation)
    manager = state["manager"]
    outstanding = state["required"] + state["optional"]
    if not outstanding:
        if not quiet:
            print("Everything Protoke needs is already installed.")
        return True

    if not quiet:
        print(BANNER)
        print()
        for key, purpose in state["required"]:
            print(f"  {key:<10} needed  — {purpose}")
        for key, purpose in state["optional"]:
            print(f"  {key:<10} extra   — {purpose}")
        print()
        if unusable_ffmpeg():
            print("There is an ffmpeg here, but it was built without the "
                  "subtitles (libass)\nfilter Protoke burns the lyrics in "
                  "with. Installing the full build fixes that.")
            print()

    keys = [key for key, _ in outstanding]
    # ffmpeg through a package manager that needs root: print it, never run it.
    if "ffmpeg" in keys and (manager is None or MANAGERS[manager]["needs_root"]):
        keys.remove("ffmpeg")
        if manager is None:
            print("Protoke could not find a package manager to install ffmpeg with.",
                  file=sys.stderr)
            print("On macOS, Homebrew is the usual one: https://brew.sh", file=sys.stderr)
        elif not quiet:
            print("Installing ffmpeg needs root, so Protoke will not run it for "
                  "you. Copy this:\n")
            print("  " + describe("ffmpeg", manager))
            print()
    if not keys:
        return not state["required"]

    if not assume_yes:
        for key in keys:
            print(f"  {describe(key, manager, separation)}")
        print()
        what = "it" if len(keys) == 1 else f"all {len(keys)} of these"
        tools = sorted({MANAGERS[manager]["label"] if key == "ffmpeg" else "pip" for key in keys})
        try:
            answer = input(f"Install {what} with {' and '.join(tools)}? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return not state["required"]
        if answer in {"n", "no"}:
            print("\nNothing installed. Starting Protoke will ask again.")
            return not state["required"]

    print()
    results = install(keys, manager, separation)
    print()
    for key, ok, detail in results:
        if ok:
            print(f"  ✓ {key}")
        else:
            print(f"  ✗ {key:<10} {detail}", file=sys.stderr)
            print(f"    try by hand: {describe(key, manager, separation)}", file=sys.stderr)
    return ready()


def ready():
    """True when nothing Protoke cannot work without is missing."""
    return platform_support.find_ffmpeg() is not None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        # For the launchers: silent, and the exit code is the answer. Only
        # what Protoke cannot work without counts, as in siphon and Media
        # Preflight: timed JSON beside a track needs no engine, so declining
        # it must not turn every start into the same question.
        return 0 if ready() else 1
    return 0 if offer(assume_yes="--yes" in argv or "-y" in argv,
                      separation="--with-separation" in argv) else 1


if __name__ == "__main__":
    sys.exit(main())
