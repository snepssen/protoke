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

How it asks is workshop-core's `Bootstrap` (`workshop/`, synced in, never
edited here), shared with siphon and Media Preflight. What is Protoke's is
below: ffmpeg found by its libass probe, the engine and separation installed
by pip into `.venv` rather than by a package manager, and the words.
"""

import os
import platform
import shutil
import subprocess
import sys

import platform_support
from workshop import bootstrap as _shared
from workshop.bootstrap import Bootstrap
from workshop.programs import MANAGERS, Program, Registry

HERE = os.path.dirname(os.path.abspath(__file__))
BANNER = "Protoke needs a few things it does not ship."

# Homebrew's plain `ffmpeg` has no libass, so it gets the full build.
FFMPEG_PACKAGES = {"brew": "ffmpeg-full", "winget": "Gyan.FFmpeg",
                   "apt": "ffmpeg", "dnf": "ffmpeg", "pacman": "ffmpeg"}


def current_manager():
    """The distribution's own manager first on Linux, as Protoke always had it."""
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


def ffmpeg_command(manager):
    return MANAGERS[manager]["command"] + [FFMPEG_PACKAGES[manager]]


def engine_steps(separation=False):
    steps = []
    if not os.path.exists(venv_python()):
        steps.append([sys.executable, "-m", "venv", os.path.join(HERE, ".venv")])
    steps.append([venv_python(), "-m", "pip", "install", "--upgrade", "pip"])
    steps.append([venv_python(), "-m", "pip", "install", *engine_packages(separation)])
    return steps


def run(argv, on_line):
    return _shared.run(argv, on_line)


# Every lookup below goes through this module's names at call time, so a test
# that replaces one of them is the one asked.
def _programs(separation):
    table = {
        "ffmpeg": Program(
            "ffmpeg", ("ffmpeg",), "burns the lyrics into the video (with libass)", True,
            FFMPEG_PACKAGES, version_args=("-version",),
            locator=lambda: platform_support.find_ffmpeg()),
        "engine": Program(
            "engine", (), "transcribes the vocal so the words land on time", False,
            locator=lambda: venv_python() if has_engine() else None,
            steps=lambda: engine_steps(separation), via="pip", version_args=None),
    }
    if separation:
        table["separation"] = Program(
            "separation", (), "isolates the voice for wordless singing (~1 GB)", False,
            locator=lambda: venv_python() if has_separation() else None,
            steps=lambda: engine_steps(separation), via="pip", version_args=None)
    return table


def _note():
    if unusable_ffmpeg():
        return ("There is an ffmpeg here, but it was built without the "
                "subtitles (libass)\nfilter Protoke burns the lyrics in "
                "with. Installing the full build fixes that.")
    return None


def _setup(separation=False):
    return Bootstrap(
        Registry(_programs(separation), "Protoke"),
        banner=BANNER,
        again="Starting Protoke will ask again.",
        note=_note,
        manager=lambda: current_manager(),
        runner=lambda argv, on_line=None: run(argv, on_line or (lambda line: None)),
    )


def survey(separation=False):
    """What is missing: ffmpeg is needed, the engine is an extra."""
    state = _setup(separation).survey()
    return {"manager": state["manager"],
            "required": [(p.key, p.purpose) for p in state["required"]],
            "optional": [(p.key, p.purpose) for p in state["optional"]]}


def offer(assume_yes=False, quiet=False, separation=False):
    """Show what is missing and install it. True when nothing needed is left."""
    return _setup(separation).offer(assume_yes=assume_yes, quiet=quiet)


def ready():
    """True when nothing Protoke cannot work without is missing."""
    return _setup().ready()


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
