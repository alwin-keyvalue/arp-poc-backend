from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tr",
    "td",
    "th",
    "ul",
}


def html_to_text(html: str) -> str:
    if not html or not html.strip():
        return ""

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "head", "meta"]):
        tag.decompose()

    text = _render_node(soup.body or soup)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _render_node(node: Tag | NavigableString) -> str:
    if isinstance(node, NavigableString):
        return str(node)

    if node.name == "br":
        return "\n"

    if node.name == "hr":
        return "\n-----Original Message-----\n"

    parts: list[str] = []
    for child in node.children:
        parts.append(_render_node(child))

    content = "".join(parts)
    if node.name in BLOCK_TAGS and content and not content.endswith("\n"):
        content += "\n"
    return content
