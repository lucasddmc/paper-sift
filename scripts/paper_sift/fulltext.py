"""Full-text stage: find open PDFs, download them, and ask the full-text questions.
The text goes only to Jev; nothing here prints it."""
import pathlib
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from .net import AuthError, HttpError, request
from .pdftext import MIN_CHARS, prepare
from .spec import question_hash


def lookup(recs, s2):
    """{paperId: {"url": PDF url or None, "authors": [names]}}. arXiv first, then S2's open-access link."""
    if not recs:
        return {}
    info = s2.batch([r["paperId"] for r in recs], fields="authors,openAccessPdf")
    out = {}
    for rec, meta in zip(recs, info):
        meta = meta or {}
        arxiv = (rec.get("externalIds") or {}).get("ArXiv")
        url = f"https://arxiv.org/pdf/{arxiv}" if arxiv else (meta.get("openAccessPdf") or {}).get("url")
        out[rec["paperId"]] = {"url": url or None,
                               "authors": [a["name"] for a in meta.get("authors") or [] if a.get("name")]}
    return out


def download(url, dest, *, transport=None, sleep=time.sleep):
    """The cached or freshly downloaded PDF, or None when the URL does not serve a PDF."""
    dest = pathlib.Path(dest)
    if dest.exists() and dest.read_bytes()[:4] == b"%PDF":
        return dest
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None
        url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc,
                                       urllib.parse.quote(parsed.path, safe=":/?#[]@!$&'()*+,;=%~"),
                                       urllib.parse.quote(parsed.query, safe=":/?#[]@!$&'()*+,;=%~"),
                                       parsed.fragment))
        data = request("GET", url, transport=transport, sleep=sleep, retries=2, timeout=90)
    except (HttpError, ValueError):
        return None
    if data[:4] != b"%PDF":
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def ask_text(rec, text, spec, ask):
    """Ask the full-text questions; on an HTTP error retry once with half the text."""
    questions = spec["fulltext_questions"]
    last = None
    for size in (len(text), len(text) // 2):
        state = {"area": spec["area"], "paper": {"title": rec.get("title") or "", "text": text[:size]}}
        try:
            out = ask(state, questions)
        except AuthError:
            raise
        except HttpError as e:
            last = e
            continue
        return {"answers": out["answers"], "tokens": out["tokens"], "model": out["model"], "chars": size,
                "hashes": {name: question_hash(q) for name, q in questions.items()}}
    return {"error": repr(last)[:300]}


def run(selected, spec, s2, ask, cache, done, *, extract, transport=None, sleep=time.sleep, log=print, workers=6):
    """Results by paperId with status read | no_pdf | no_text | error."""
    hashes = {name: question_hash(q) for name, q in spec["fulltext_questions"].items()}
    results = dict(done)
    todo = [r for r in selected
            if not (done.get(r["paperId"], {}).get("status") == "read"
                    and done[r["paperId"]].get("hashes") == hashes)]
    meta = lookup(todo, s2)
    texts = {}
    for r in todo:
        pid, info = r["paperId"], meta[r["paperId"]]
        base = {"url": info["url"], "authors": info["authors"]}
        path = pathlib.Path(cache) / f"{pid}.pdf"
        fresh = not path.exists()
        got = download(info["url"], path, transport=transport, sleep=sleep) if info["url"] else None
        if info["url"] and fresh:
            sleep(3.0 if "arxiv.org" in info["url"] else 1.0)  # arXiv asks for 3 s between requests
        if not got:
            results[pid] = {**base, "status": "no_pdf"}
            log(f"no open PDF: {(r.get('title') or pid)[:70]}")
            continue
        try:
            body, was_cut, total = prepare(extract(got))
        except ImportError:
            raise
        except Exception as e:  # broken or encrypted PDF
            results[pid] = {**base, "status": "no_text", "error": repr(e)[:200]}
            continue
        if len(body.strip()) < MIN_CHARS:
            results[pid] = {**base, "status": "no_text", "chars_pdf": total}
            continue
        texts[pid] = (r, body, base, was_cut, total)

    def one(item):
        pid, (r, body, base, was_cut, total) = item
        try:
            out = ask_text(r, body, spec, ask)
        except AuthError:
            raise
        except Exception as e:
            return pid, {**base, "status": "error", "error": type(e).__name__, "cut_references": was_cut,
                         "chars_pdf": total}
        return pid, {**base, "status": "error" if "error" in out else "read", "cut_references": was_cut,
                     "chars_pdf": total, **out}

    with ThreadPoolExecutor(workers) as executor:
        for pid, res in executor.map(one, texts.items()):
            results[pid] = res
    return results
