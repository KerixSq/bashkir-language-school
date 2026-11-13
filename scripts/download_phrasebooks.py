"""Download the audited corpus revision, verifying each SHA-256; never overwrite edits."""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', type=Path, default=ROOT / 'data/phrasebooks')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'docs/CORPUS_PROVENANCE.json').read_text(encoding='utf-8'))
    args.dir.mkdir(parents=True, exist_ok=True)
    base = (
        'https://huggingface.co/datasets/bashkorttele/trilingual-parallel-phrasebooks-bgpu/resolve/'
    )
    for name, digest in manifest['files'].items():
        path = args.dir / Path(name).name
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise SystemExit(f'{path.name}: existing content differs; choose a new --dir')
            print('OK', path.name)
            continue
        with urllib.request.urlopen(
            base + manifest['revision'] + '/' + name, timeout=60
        ) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != digest:
            raise SystemExit(f'{path.name}: SHA-256 mismatch; file was not saved')
        with path.open('xb') as target:
            target.write(content)
        print('DOWNLOADED', path.name)


if __name__ == '__main__':
    main()
