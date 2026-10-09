"""Where API keys live: an environment variable first, then a file only the user can read."""
import os
import pathlib

SERVICES = {
    "typesafe": ("TYPESAFE_API_KEY", (".config", "typesafe", "key")),
    "s2": ("S2_API_KEY", (".config", "semanticscholar", "key")),
}


class KeyFormatError(ValueError):
    """A stored key that cannot go into an HTTP header. It names the service and where the key came from
    (the environment variable or the file), never the value."""

    def __init__(self, service, source):
        self.service, self.source = service, str(source)
        super().__init__(f"the {service} key in {source} contains spaces, line breaks, control or non-ASCII "
                         "characters")


def well_formed(value):
    """True when every character is printable ASCII other than a space, as an HTTP header value needs."""
    return all("!" <= c <= "~" for c in value)


def clean(value):
    """The key without surrounding whitespace; ValueError when it is empty or cannot be a key."""
    value = value.strip()
    if not value:
        raise ValueError("empty key")
    if not well_formed(value):
        raise ValueError("key contains spaces, line breaks or non-ASCII characters")
    return value


def key_path(service, home=None):
    _, parts = SERVICES[service]
    return pathlib.Path(home or pathlib.Path.home()).joinpath(*parts)


def get_key(service, env=None, home=None):
    """The key, or None when there is none. KeyFormatError when the stored value cannot be a key."""
    env = os.environ if env is None else env
    var, _ = SERVICES[service]
    value = (env.get(var) or "").strip()
    if value:
        if not well_formed(value):
            raise KeyFormatError(service, var)
        return value
    path = key_path(service, home)
    if path.exists():
        value = path.read_bytes().decode("ascii", "replace").strip()  # other bytes become U+FFFD: malformed
        if value and not well_formed(value):
            raise KeyFormatError(service, path)
        return value or None
    return None


def save_key(service, value, home=None):
    value = clean(value)
    path = key_path(service, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)
    os.chmod(path, 0o600)
    return path
