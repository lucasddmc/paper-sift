"""pypdf on demand: installed into a private venv in the plugin's data directory, never system-wide."""
import os
import pathlib
import subprocess
import venv

REQUIREMENT = "pypdf>=4"


def data_dir(given=None):
    """The plugin data directory, or ~/.cache/paper-sift when the skill could not substitute it."""
    if given and "${" not in given:
        return pathlib.Path(given).expanduser()
    return pathlib.Path.home() / ".cache" / "paper-sift"


def have_pypdf():
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return False
    return True


def venv_python(base):
    return pathlib.Path(base) / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_pypdf(base, *, log=print):
    """None if pypdf imports here; otherwise the path of a venv Python that has it (created on first use)."""
    if have_pypdf():
        return None
    python = venv_python(base)
    try:
        if not python.exists():
            log(f"First full-text run: installing {REQUIREMENT} into {python.parent.parent} ...")
            venv.EnvBuilder(with_pip=True).create(str(python.parent.parent))
        if subprocess.run([str(python), "-c", "import pypdf"], capture_output=True).returncode != 0:
            subprocess.run([str(python), "-m", "pip", "install", "--quiet", REQUIREMENT], check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise RuntimeError(f"could not install {REQUIREMENT} ({e}). Install it with "
                           f"`python3 -m pip install --user '{REQUIREMENT}'` and run the step again.") from None
    return python
