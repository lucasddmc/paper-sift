"""Files of a survey directory. JSON everywhere; the pool is gzipped; scores are append-only lines."""
import gzip
import json
import pathlib

FILES = {
    "spec": "spec.json", "pool": "pool.json.gz", "pool_partial": "pool.partial.json.gz", "scores": "scores.jsonl",
    "fulltext": "fulltext.json",
    "sample": "validation/sample.json", "sample_key": "validation/key.json", "labels": "validation/labels.json",
    "validation": "validation/result.json", "report": "report.md", "bib": "reading-list.bib", "csv": "scored.csv",
}


class Survey:
    def __init__(self, directory):
        self.dir = pathlib.Path(directory)

    def path(self, name):
        return self.dir / FILES[name]

    def exists(self, name):
        return self.path(name).exists()

    def read(self, name, default=None):
        p = self.path(name)
        if not p.exists():
            return default
        data = p.read_bytes()
        return json.loads(gzip.decompress(data) if p.suffix == ".gz" else data)

    def write(self, name, obj):
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(obj, ensure_ascii=False, indent=1).encode()
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(gzip.compress(data) if p.suffix == ".gz" else data)
        tmp.replace(p)

    def read_lines(self, name):
        p = self.path(name)
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]

    def append_lines(self, name, rows):
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def write_text(self, name, text):
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
