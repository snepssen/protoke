from pathlib import Path
import io
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock


TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))

import bootstrap  # noqa: E402


def quietly(function, *args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        result = function(*args, **kwargs)
    return result, out.getvalue() + err.getvalue()


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg = mock.patch.object(bootstrap.platform_support, "find_ffmpeg", return_value=None)
        self.engine = mock.patch.object(bootstrap, "has_engine", return_value=False)
        self.ffmpeg.start(); self.engine.start()
        self.addCleanup(self.ffmpeg.stop); self.addCleanup(self.engine.stop)

    def test_ffmpeg_is_needed_and_the_engine_is_an_extra(self):
        with mock.patch.object(bootstrap, "current_manager", return_value="brew"):
            state = bootstrap.survey()
        self.assertEqual([key for key, _ in state["required"]], ["ffmpeg"])
        self.assertEqual([key for key, _ in state["optional"]], ["engine"])

    def test_separation_is_offered_only_when_asked_for(self):
        with mock.patch.object(bootstrap, "has_separation", return_value=False):
            self.assertNotIn("separation", [k for k, _ in bootstrap.survey()["optional"]])
            self.assertIn("separation", [k for k, _ in bootstrap.survey(separation=True)["optional"]])
        self.assertNotIn("audio-separator[cpu]", bootstrap.engine_packages())
        self.assertIn("audio-separator[cpu]", bootstrap.engine_packages(separation=True))

    def test_homebrew_gets_the_build_with_libass(self):
        # Plain `ffmpeg` on Homebrew has no subtitles filter.
        self.assertEqual(bootstrap.ffmpeg_command("brew"), ["brew", "install", "ffmpeg-full"])

    def test_a_root_package_manager_is_printed_never_run(self):
        ran = []
        with mock.patch.object(bootstrap, "current_manager", return_value="apt"), \
                mock.patch.object(bootstrap, "run", side_effect=lambda argv, on_line: ran.append(argv)), \
                mock.patch.object(bootstrap, "engine_steps", return_value=[["pip", "install", "x"]]):
            ok, said = quietly(bootstrap.offer, assume_yes=True)
        self.assertFalse(ok, "ffmpeg is still missing")
        self.assertIn("sudo apt-get install -y ffmpeg", said)
        self.assertTrue(all("sudo" not in argv for argv in ran), ran)
        self.assertEqual(ran, [["pip", "install", "x"]], "the engine still installs")

    def test_a_bare_enter_installs_everything(self):
        ran = []
        with mock.patch.object(bootstrap, "current_manager", return_value="brew"), \
                mock.patch.object(bootstrap, "run", side_effect=lambda argv, on_line: ran.append(argv)), \
                mock.patch.object(bootstrap, "engine_steps", return_value=[["pip", "install", "x"]]), \
                mock.patch("builtins.input", return_value=""):
            quietly(bootstrap.offer)
        self.assertEqual(ran, [["brew", "install", "ffmpeg-full"], ["pip", "install", "x"]])

    def test_no_installs_nothing(self):
        with mock.patch.object(bootstrap, "current_manager", return_value="brew"), \
                mock.patch.object(bootstrap, "run") as run, \
                mock.patch("builtins.input", return_value="n"):
            ok, said = quietly(bootstrap.offer)
        run.assert_not_called()
        self.assertFalse(ok)
        self.assertIn("Nothing installed", said)

    def test_an_ffmpeg_without_libass_is_named_as_such(self):
        with mock.patch.object(bootstrap.shutil, "which", return_value="/usr/bin/ffmpeg"), \
                mock.patch.object(bootstrap, "current_manager", return_value="brew"), \
                mock.patch("builtins.input", return_value="n"):
            _, said = quietly(bootstrap.offer)
        self.assertIn("built without the subtitles (libass)", said)

    def test_the_launch_check_asks_only_about_what_is_needed(self):
        self.assertEqual(bootstrap.main(["--check"]), 1)
        with mock.patch.object(bootstrap.platform_support, "find_ffmpeg", return_value="/x/ffmpeg"):
            # Declining the engine must not turn every start into the question.
            self.assertEqual(bootstrap.main(["--check"]), 0)

    def test_nothing_missing_says_so(self):
        with mock.patch.object(bootstrap.platform_support, "find_ffmpeg", return_value="/x/ffmpeg"), \
                mock.patch.object(bootstrap, "has_engine", return_value=True):
            ok, said = quietly(bootstrap.offer)
        self.assertTrue(ok)
        self.assertIn("already installed", said)


if __name__ == "__main__":
    unittest.main()
