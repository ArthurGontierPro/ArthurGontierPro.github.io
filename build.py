#!/usr/bin/env python3
"""Generate the English and French pages from src/index.html.

Every translatable node in the source carries its French text in a data-fr
attribute (data-fr-aria-label for the one translated attribute). That was
originally a runtime mechanism; here it is the source format instead, so each
language gets its own crawlable URL:

    src/index.html  ->  index.html      (English, /)
                    ->  fr/index.html   (French,  /fr/)

Run  python3 build.py  after editing src/index.html, then commit both outputs.
"""

import io
import os
import re
import sys

SRC = 'src/index.html'
SITE = 'https://arthurgontierpro.github.io/'

PAGES = {
    'en': {
        'out': 'index.html',
        'prefix': '',
        'url': SITE,
        'locale': 'en_GB',
        'locale_alt': 'fr_FR',
        'desc': 'Arthur Gontier - postdoctoral researcher, FATA section, '
                'University of Glasgow. Constraint solvers, proof logging, cryptanalysis.',
        'card': 'Postdoctoral researcher, FATA section, University of Glasgow. '
                'Constraint solvers, proof logging, cryptanalysis.',
    },
    'fr': {
        'out': 'fr/index.html',
        'prefix': '../',
        'url': SITE + 'fr/',
        'locale': 'fr_FR',
        'locale_alt': 'en_GB',
        'desc': 'Arthur Gontier - chercheur postdoctoral, section FATA, '
                'université de Glasgow. Solveurs de contraintes, preuves '
                'vérifiables, cryptanalyse.',
        'card': 'Chercheur postdoctoral, section FATA, université de Glasgow. '
                'Solveurs de contraintes, preuves vérifiables, cryptanalyse.',
    },
}

# The little link pills are plain words, so they are translated by lookup rather
# than by carrying a data-fr each.
PILLS_FR = {
    'pdf': 'pdf',
    'code': 'code',
    'slides': 'slides',     # "transparents" is correct but nobody says it
    'talk': 'exposé',
    'defence': 'soutenance',
}

# Links shared before the site became bilingual carried ?lang=fr; keep them working.
LANG_REDIRECT = """<script>
/* Before the French version had its own URL the language was carried in a query
   string. Those links are still out there, so honour them. */
if (/[?&]lang=fr\\b/.test(location.search)) {
	location.replace('fr/' + location.hash);
}
</script>"""


def open_tag_end(html, tag_start):
    """Offset just past the '>' that closes an opening tag, skipping over any
    quoted attribute value. The data-fr values contain markup of their own, so
    a plain search for the next '>' would stop inside one."""
    i = tag_start + 1
    while True:
        c = html[i]
        if c in '"\'':
            i = html.index(c, i + 1) + 1
        elif c == '>':
            return i + 1
        else:
            i += 1


def find_element(html, attr_pos):
    """Given the offset of an attribute, return (open_tag_start, inner_start,
    inner_end, tag_end) for the element that carries it."""
    start = html.rindex('<', 0, attr_pos)
    tag = re.match(r'<([a-zA-Z0-9]+)', html[start:]).group(1)
    inner_start = open_tag_end(html, start)
    assert inner_start > attr_pos, 'tag boundary resolved before the attribute'

    # Walk forward counting same-name tags, so nesting (a span inside a span)
    # resolves to the right closing tag.
    depth = 1
    pos = inner_start
    open_re = re.compile(r'<%s[\s>]' % tag, re.I)
    close = '</%s>' % tag
    while depth:
        nxt_close = html.index(close, pos)
        m = open_re.search(html, pos, nxt_close)
        if m:
            depth += 1
            pos = m.end()
        else:
            depth -= 1
            pos = nxt_close + len(close)
    return start, inner_start, nxt_close, pos


def apply_translations(html, lang):
    """Replace each element's content with its French text, or drop the French
    text, depending on the language being built."""
    # Content: data-fr='...'
    attr_re = re.compile(r"\sdata-fr='(.*?)'(?=[\s>])", re.S)
    while True:
        m = attr_re.search(html)
        if not m:
            break
        _, inner_start, inner_end, _ = find_element(html, m.start())
        body = m.group(1) if lang == 'fr' else html[inner_start:inner_end]
        # Drop the attribute, keep the rest of the opening tag, then the chosen body.
        html = html[:m.start()] + html[m.end():inner_start] + body + html[inner_end:]

    # Attributes: data-fr-aria-label='...' / "..."
    def swap_attr(m):
        value = m.group(2)
        return ' aria-label="%s"' % value if lang == 'fr' else ''
    html = re.sub(r'\sdata-fr-aria-label=(["\'])(.*?)\1', swap_attr, html)
    if lang == 'fr':
        # The English aria-label it replaces is now a duplicate; drop the first.
        html = re.sub(r'\saria-label="Back to top"(?=.*\saria-label=")', '', html)

    # Pills
    if lang == 'fr':
        def pill(m):
            return m.group(1) + PILLS_FR.get(m.group(2).lower(), m.group(2)) + m.group(3)
        html = re.sub(r'(<a href="[^"]*">)([A-Za-z]+)(</a>)',
                      lambda m: pill(m) if m.group(2).lower() in PILLS_FR else m.group(0),
                      html)
    return html


def retarget_paths(html, prefix):
    """Rewrite root-relative asset references for a page served from /fr/."""
    if not prefix:
        return html
    html = re.sub(r'(\s(?:href|src|srcset)=")(assets/|images/|pdf/|favicon[\w.-]*\.(?:ico|png)|apple-touch-icon\.png)', r'\1' + prefix + r'\2', html)
    html = re.sub(r'(url\((["\']?))(assets/)', r'\1' + prefix + r'\3', html)
    return html


def build(lang):
    cfg = PAGES[lang]
    html = io.open(SRC, encoding='utf-8').read()

    html = apply_translations(html, lang)
    html = retarget_paths(html, cfg['prefix'])

    html = html.replace('<html lang="en">', '<html lang="%s">' % lang)
    html = html.replace('@@URL@@', cfg['url'])
    html = html.replace('@@DESC@@', cfg['desc'])
    html = html.replace('@@CARD@@', cfg['card'])
    html = html.replace('@@LOCALE_ALT@@', cfg['locale_alt'])
    html = html.replace('@@LOCALE@@', cfg['locale'])
    html = html.replace('@@LANGREDIRECT@@', LANG_REDIRECT if lang == 'en' else '')

    # './' rather than '' for the self-link: an empty href re-resolves to the
    # current URL query string and all, which would re-fire the ?lang=fr redirect.
    html = html.replace('@@HREF_EN@@', './' if lang == 'en' else '../')
    html = html.replace('@@HREF_FR@@', 'fr/' if lang == 'en' else './')
    html = html.replace('@@CLASS_EN@@', ' class="active" aria-current="page"' if lang == 'en' else '')
    html = html.replace('@@CLASS_FR@@', ' class="active" aria-current="page"' if lang == 'fr' else '')

    leftovers = re.findall(r'@@[A-Z_]+@@|data-fr', html)
    if leftovers:
        sys.exit('unsubstituted markers in %s: %s' % (cfg['out'], set(leftovers)))

    out = cfg['out']
    if os.path.dirname(out):
        try:
            os.makedirs(os.path.dirname(out))
        except OSError:
            pass
    io.open(out, 'w', encoding='utf-8').write(html)
    print('wrote %-16s %6d bytes' % (out, len(html.encode('utf-8'))))


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
	<url>
		<loc>%(site)s</loc>
		<xhtml:link rel="alternate" hreflang="en" href="%(site)s" />
		<xhtml:link rel="alternate" hreflang="fr" href="%(site)sfr/" />
	</url>
	<url>
		<loc>%(site)sfr/</loc>
		<xhtml:link rel="alternate" hreflang="en" href="%(site)s" />
		<xhtml:link rel="alternate" hreflang="fr" href="%(site)sfr/" />
	</url>
</urlset>
""" % {'site': SITE}

if __name__ == '__main__':
    for lang in ('en', 'fr'):
        build(lang)
    io.open('sitemap.xml', 'w', encoding='utf-8').write(SITEMAP)
    print('wrote sitemap.xml')
