from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, NavigableString, Tag

from app.email.disclaimer import strip_regulatory_disclaimer
from app.email.html_to_text import html_to_text

GMAIL_QUOTE_CLASSES = {"gmail_quote", "gmail_quote_container"}
OUTLOOK_REPLY_CONTAINER_IDS = {"divrplyfwdmsg"}
OUTLOOK_REPLY_CONTAINER_PREFIXES = ("divrplyfwdmsg", "x_divrplyfwdmsg")

ON_WROTE_RE = re.compile(r"^On .+ wrote:\s*$", re.IGNORECASE | re.MULTILINE)
FROM_SENT_SUBJECT_RE = re.compile(
    r"^From:\s*.+\n(?:Sent|Date):\s*.+\n(?:To:\s*.+\n)?(?:Cc:\s*.+\n)?Subject:\s*.+",
    re.IGNORECASE | re.MULTILINE,
)
ORIGINAL_MESSAGE_RE = re.compile(r"^-{2,}\s*Original Message\s*-{2,}$", re.IGNORECASE | re.MULTILINE)


@dataclass
class SplitEmailBody:
    body_text: str
    parent_email_body: str | None = None
    forwarded_email_body: str | None = None


def split_email_body(
    *,
    html: str | None,
    text: str | None,
    is_reply: bool,
    is_forwarded: bool,
) -> SplitEmailBody:
    if html:
        soup = _prepare_html_soup(html)
        boundary = _find_html_boundary(soup)
        if boundary is not None:
            body_html, quoted_html = _split_html_at_boundary(soup, boundary)
            body_text = _clean_body_text(html_to_text(body_html))
            quoted_text = html_to_text(quoted_html).strip()
            parent_from_html = _extract_parent_from_quoted_html(quoted_html) if is_reply else None
            result = _build_split_result(body_text, quoted_text, is_reply=is_reply, is_forwarded=is_forwarded)
            if parent_from_html:
                result.parent_email_body = parent_from_html
            return result

    plain = text or (html_to_text(html) if html else "")
    return _split_plain_text(plain, is_reply=is_reply, is_forwarded=is_forwarded)


def _prepare_html_soup(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.select('.gmail_signature, [data-smartmail="gmail_signature"]'):
        tag.decompose()
    return soup


def _extract_parent_from_quoted_html(quoted_html: str) -> str | None:
    soup = BeautifulSoup(quoted_html, "lxml")
    blockquote = soup.find(
        "blockquote",
        class_=lambda value: value and any("gmail_quote" in cls for cls in value),
    )
    if not blockquote:
        return None

    for tag in blockquote.select('.gmail_signature, [data-smartmail="gmail_signature"]'):
        tag.decompose()

    text = html_to_text(str(blockquote)).strip()
    lines = text.splitlines()
    while lines and (not lines[0].strip() or ON_WROTE_RE.match(lines[0].strip())):
        lines.pop(0)
    cleaned = _clean_body_text("\n".join(lines))
    return cleaned or None


def _find_html_boundary(soup: BeautifulSoup) -> Tag | None:
    container = soup.body or soup
    for element in container.descendants:
        if not isinstance(element, Tag):
            continue
        if _is_boundary_tag(element):
            return element
    return None


def _is_boundary_tag(tag: Tag) -> bool:
    tag_id = str(tag.get("id", "")).lower()
    if tag_id in OUTLOOK_REPLY_CONTAINER_IDS or any(
        tag_id.startswith(prefix) for prefix in OUTLOOK_REPLY_CONTAINER_PREFIXES
    ):
        return True

    classes = {cls.lower() for cls in tag.get("class", [])}
    if classes & GMAIL_QUOTE_CLASSES:
        return True

    return tag.name == "hr"


def _contains_boundary(node: Tag | NavigableString, boundary: Tag) -> bool:
    if node is boundary:
        return True
    return isinstance(node, Tag) and boundary in node.descendants


def _split_html_at_boundary(soup: BeautifulSoup, boundary: Tag) -> tuple[str, str]:
    body_container = soup.body or soup
    quoted_container = soup.new_tag("div")
    moving = False

    for child in list(body_container.children):
        if _contains_boundary(child, boundary):
            moving = True
        if moving:
            quoted_container.append(child.extract())

    return str(body_container), str(quoted_container)


def _split_plain_text(
    plain: str,
    *,
    is_reply: bool,
    is_forwarded: bool,
) -> SplitEmailBody:
    normalized = plain.replace("\r\n", "\n").replace("\r", "\n")
    split_index = _find_plain_boundary_index(normalized)

    if split_index is None:
        return SplitEmailBody(body_text=_clean_body_text(normalized))

    body_text = _clean_body_text(normalized[:split_index])
    quoted_text = normalized[split_index:].strip()
    return _build_split_result(body_text, quoted_text, is_reply=is_reply, is_forwarded=is_forwarded)


def _build_split_result(
    body_text: str,
    quoted_text: str,
    *,
    is_reply: bool,
    is_forwarded: bool,
) -> SplitEmailBody:
    if is_forwarded:
        return SplitEmailBody(
            body_text=body_text,
            forwarded_email_body=_format_forwarded_body(quoted_text) if quoted_text else None,
        )

    if is_reply:
        return SplitEmailBody(
            body_text=body_text,
            parent_email_body=_extract_immediate_parent(quoted_text) if quoted_text else None,
        )

    return SplitEmailBody(body_text=body_text or quoted_text)


def _find_plain_boundary_index(text: str) -> int | None:
    patterns = [
        ORIGINAL_MESSAGE_RE,
        re.compile(r"^_{5,}$", re.MULTILINE),
        FROM_SENT_SUBJECT_RE,
        ON_WROTE_RE,
    ]
    indices = []
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            indices.append(match.start())
    return min(indices) if indices else None


def _extract_immediate_parent(quoted_text: str) -> str:
    lines = quoted_text.splitlines()
    header_end = 0
    for index, line in enumerate(lines):
        if not line.strip():
            header_end = index + 1
            break
        if line.lower().startswith("subject:"):
            header_end = index + 1
            break

    body_lines = lines[header_end:]
    if not body_lines:
        return quoted_text.strip()

    nested_text = "\n".join(body_lines)
    nested_boundary = _find_plain_boundary_index(nested_text)
    if nested_boundary is not None and nested_boundary > 0:
        body_lines = nested_text[:nested_boundary].splitlines()

    parent_body = "\n".join(line for line in body_lines if line.strip()).strip()
    return parent_body or quoted_text.strip()


def _format_forwarded_body(quoted_text: str) -> str:
    lines = [line.strip() for line in quoted_text.splitlines() if line.strip()]
    if not lines:
        return quoted_text.strip()

    from_line = next((line for line in lines if line.lower().startswith("from:")), None)
    subject_line = next((line for line in lines if line.lower().startswith("subject:")), None)

    body_start = 0
    for index, line in enumerate(lines):
        if line.lower().startswith("subject:"):
            body_start = index + 1
            break

    body = "\n".join(lines[body_start:]).strip()
    if from_line and subject_line:
        return f"{from_line}\n{subject_line}\n\n{body}".strip()
    return quoted_text.strip()


def _clean_body_text(text: str) -> str:
    cleaned = strip_regulatory_disclaimer(text.strip())
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned
