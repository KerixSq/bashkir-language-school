#!/usr/bin/env python3
"""Apply the brand refresh to the *current* working tree, not an old ZIP.

Usage: python scripts/apply_brand_update.py
The script only edits web/index.html. New assets are committed separately.
"""

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / 'web/index.html'
ASSETS = ROOT / 'web/assets'


def replace_exact(regex, replacement, document, label):
    changed, count = re.subn(regex, replacement, document, count=1, flags=re.S)
    if count != 1:
        raise ValueError(
            f'{label}: expected one matching element, got {count}. Check current HTML.'
        )
    return changed


def main():
    for filename in ('akbuzat-chibi.webp', 'bashkir-mark.svg'):
        if not (ASSETS / filename).exists():
            raise SystemExit(f'Missing asset: web/assets/{filename}')
    if not HTML.exists():
        raise SystemExit('web/index.html not found; run from the repository root.')
    original = HTML.read_text(encoding='utf-8-sig')
    text = original
    # The block's next sibling makes this match unambiguous; it cannot eat other sections.
    if 'class="legend-zone"' in text:
        text = replace_exact(
            r'\s*<section class="legend-zone"[^>]*>.*?</section>(?=\s*<section id="start-guide")',
            '',
            text,
            'legends section',
        )
    if 'Герои башкирских легенд' in text:
        raise ValueError('Legends section has changed: stopped without writing.')

    # Remove now-unused single-selector legend rules while retaining shared styles.
    def remove_legend_rule(match):
        selectors = match.group(0).split('{', 1)[0].strip().split(',')
        return (
            ''
            if all(selector.strip().startswith('.legend-') for selector in selectors)
            else match.group(0)
        )

    text = re.sub(r'(?m)^[ \t]*\.legend-[^\r\n]*(?:\r?\n|$)', remove_legend_rule, text)
    if 'src="assets/bashkir-mark.svg"' not in text:
        text = replace_exact(
            r'(<span class="app-brand-icon"[^>]*>\s*<img\s+)src="assets/akbuzat\.webp"',
            r'\1src="assets/bashkir-mark.svg"',
            text,
            'brand icon',
        )
    if '<div class="app-sidebar-bottom">' in text and not re.search(
        r'<div class="app-sidebar-bottom">\s*<img[^>]*src="assets/akbuzat-chibi.webp"', text
    ):
        text = replace_exact(
            r'(<div class="app-sidebar-bottom">\s*<img\s+)src="assets/akbuzat\.webp"',
            r'\1src="assets/akbuzat-chibi.webp"',
            text,
            'sidebar chibi',
        )
    if 'class="app-guide-illustration"' in text and not re.search(
        r'class="app-guide-illustration"[^>]*>\s*<img[^>]*src="assets/akbuzat-chibi.webp"', text
    ):
        text = replace_exact(
            r'(<div class="app-guide-illustration"[^>]*>\s*<img\s+)src="assets/akbuzat\.webp"',
            r'\1src="assets/akbuzat-chibi.webp"',
            text,
            'guide chibi',
        )
    if 'href="assets/bashkir-mark.svg"' not in text:
        text = text.replace(
            '</head>',
            '  <link rel="icon" type="image/svg+xml" href="assets/bashkir-mark.svg">\n</head>',
            1,
        )
    marker = '/* Brand refresh: geometric mark and small chibi mascot. */'
    if marker not in text:
        css = (
            f'  {marker}\n'
            '  .app-brand-icon{background:#115a74!important;border:0!important;box-shadow:none!important;overflow:hidden!important}\n'
            '  .app-brand-icon img{width:100%!important;height:100%!important;object-fit:contain!important}\n'
            '  .app-sidebar-bottom img{width:145px;height:124px;max-width:100%;object-fit:contain}\n'
            '  .app-guide-illustration img{width:118px;height:118px;max-width:100%;object-fit:contain}\n'
        )
        text = text.replace('</style>', css + '</style>', 1)
    if text == original:
        print('Already applied; no changes needed.')
        return
    # Write to a backup and atomically replace the actual HTML.
    backup = ROOT / '.index.html.before-brand-update.bak'
    if not backup.exists():
        shutil.copyfile(HTML, backup)
    temp = HTML.with_suffix('.html.tmp')
    temp.write_text(text, encoding='utf-8')
    temp.replace(HTML)
    print('Updated web/index.html. Backup in repository root:', backup.name)
    print('Removed: legends section. Added: book+kurai mark and chibi mascot.')


if __name__ == '__main__':
    main()
