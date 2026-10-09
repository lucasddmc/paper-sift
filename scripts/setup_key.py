#!/usr/bin/env python3
"""Store an API key for paper-sift. Run it in your own terminal, never inside a chat.

  python3 setup_key.py typesafe   # required; get a key at https://console.typesafe.ai/
  python3 setup_key.py s2         # optional; free key at https://www.semanticscholar.org/product/api
"""
import getpass
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from paper_sift import jev, keys  # noqa: E402
from paper_sift.net import AuthError, HttpError  # noqa: E402
from paper_sift.s2 import S2  # noqa: E402

LABELS = {"typesafe": "TypeSafe API key", "s2": "Semantic Scholar API key"}


def check(service, key):
    if service == "typesafe":
        return jev.check_key(key)
    S2(key=key, pause=0, retries=1).batch(["arXiv:1706.03762"], fields="title")
    return "Semantic Scholar"


def main(argv=None, getpass_fn=getpass.getpass, checker=check, home=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in keys.SERVICES:
        print(__doc__.strip())
        return 2
    service = argv[0]
    entered = getpass_fn(f"{LABELS[service]} (typing is hidden): ")
    if not entered.strip():
        print("No key entered; nothing was saved.")
        return 1
    try:
        value = keys.clean(entered)  # before any request: a malformed key never goes on the wire
    except ValueError:
        print("That key contains spaces, line breaks or other characters a key cannot have; nothing was saved.")
        return 1

    # Check if a previous key exists
    path = keys.key_path(service, home=home)
    previous_exists = path.exists()

    # Check the key BEFORE saving
    try:
        who = checker(service, value)
    except AuthError:
        msg = "The service rejected the key; nothing was saved."
        if previous_exists:
            msg += " Your previous key was kept."
        print(msg)
        return 1
    except HttpError as e:
        # For network errors, save the key anyway
        path = keys.save_key(service, value, home=home)
        print(f"Saved to {path}. Could not verify it now (HTTP {e.status}); it will be checked on first use.")
        return 0

    # If check succeeded, save the key
    path = keys.save_key(service, value, home=home)
    print(f"OK: key saved to {path} and accepted by {who}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
