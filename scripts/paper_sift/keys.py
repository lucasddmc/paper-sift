"""Where API keys live: an environment variable first, then a file only the user can read."""
import os
import pathlib

SERVICES = {
    "typesafe": ("TYPESAFE_API_KEY", (".config", "typesafe", "key")),
    "s2": ("S2_API_KEY", (".config", "semanticscholar", "key")),
}


def key_path(service, home=None):
    _, parts = SERVICES[service]
    return pathlib.Path(home or pathlib.Path.home()).joinpath(*parts)


def get_key(service, env=None, home=None):
    env = os.environ if env is None else env
    var, _ = SERVICES[service]
    value = (env.get(var) or "").strip()
    if value:
        return value
    path = key_path(service, home)
    if path.exists():
        return path.read_text().strip() or None
    return None


def save_key(service, value, home=None):
    value = value.strip()
    if not value:
        raise ValueError("empty key")
    path = key_path(service, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)
    os.chmod(path, 0o600)
    return path
