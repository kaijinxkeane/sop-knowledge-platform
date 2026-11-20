import wiki_core


def test_loads_canonical_script():
    assert wiki_core.SCRIPT_PATH.name == "llm-wiki"


def test_frontmatter_helpers():
    fm, body = wiki_core.split_markdown_frontmatter("---\ntitle: X\ntags: [a, b]\n---\nBody")
    assert wiki_core.parse_frontmatter_block(fm) == {"title": "X", "tags": ["a", "b"]}
    assert body.strip() == "Body"


def test_wikilink_slug():
    assert wiki_core.wikilink_slug("Programmes/Signature Brand#Intro|alias") == "signature-brand"
