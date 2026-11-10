"""Tes unit pembuatan, penyalinan, dan pembersihan run DOCX."""

import pytest
from lxml import etree

from docgen.docx.names import W_R, W_RPR, W_T, W_TAB, W_VAL
from docgen.docx.runs import (
    append_text_run,
    clone_run,
    copy_rpr,
    make_run,
    strip_bold_from_rpr,
)
from docgen.docx.xml import qn

W_B = qn("w:b")
W_BCS = qn("w:bCs")
W_I = qn("w:i")
XML_SPACE = qn("xml:space")


def _paragraph() -> etree._Element:
    return etree.Element(qn("w:p"))


def _rpr() -> etree._Element:
    return etree.Element(W_RPR)


def test_make_run_minimal() -> None:
    paragraph = _paragraph()

    run = make_run(paragraph)

    assert run.tag == W_R
    assert run.getparent() is paragraph
    assert list(run) == []


def test_make_run_with_text_and_rpr() -> None:
    paragraph = _paragraph()
    template = _rpr()
    etree.SubElement(template, W_I)

    run = make_run(paragraph, text="Halo", rpr=template)

    children = list(run)
    assert [child.tag for child in children] == [W_RPR, W_T]
    assert children[0] is not template
    assert children[0].find(W_I) is not None
    assert children[1].text == "Halo"
    assert children[1].get(XML_SPACE) is None
    assert template.getparent() is None


def test_make_run_preserves_edge_spaces_only() -> None:
    paragraph = _paragraph()

    leading = make_run(paragraph, text=" awal")
    trailing = make_run(paragraph, text="akhir ")
    inner = make_run(paragraph, text="a b")

    for run in (leading, trailing):
        node = run.find(W_T)
        assert node is not None
        assert node.get(XML_SPACE) == "preserve"
    inner_node = inner.find(W_T)
    assert inner_node is not None
    assert inner_node.get(XML_SPACE) is None


def test_append_text_run_keeps_single_rpr_before_text() -> None:
    paragraph = _paragraph()
    template = _rpr()
    etree.SubElement(template, W_I)

    run = append_text_run(paragraph, "a\tb", rpr=template)

    assert run.getparent() is paragraph
    assert [child.tag for child in run] == [W_RPR, W_T, W_TAB, W_T]
    assert len(run.findall(W_RPR)) == 1
    assert run.find(W_RPR) is not template
    assert [node.text for node in run.findall(W_T)] == ["a", "b"]

    second = append_text_run(paragraph, "c", rpr=template)
    assert len(second.findall(W_RPR)) == 1
    assert len(run.findall(W_RPR)) == 1
    assert template.getparent() is None


def test_append_text_run_without_rpr_starts_with_text() -> None:
    paragraph = _paragraph()

    run = append_text_run(paragraph, "teks")

    assert [child.tag for child in run] == [W_T]
    assert run.find(W_RPR) is None


def test_clone_run_is_independent() -> None:
    paragraph = _paragraph()
    run = make_run(paragraph, text="asli", rpr=_rpr())
    run.set(qn("w:rsidR"), "0001")

    cloned = clone_run(run)
    cloned.set(qn("w:rsidR"), "0002")
    cloned_text = cloned.find(W_T)
    cloned_rpr = cloned.find(W_RPR)
    assert cloned_text is not None
    assert cloned_rpr is not None
    cloned_text.text = "ubah"
    cloned_rpr.append(etree.Element(W_I))

    assert cloned is not run
    assert cloned.getparent() is None
    assert run.get(qn("w:rsidR")) == "0001"
    original_text = run.find(W_T)
    original_rpr = run.find(W_RPR)
    assert original_text is not None
    assert original_rpr is not None
    assert original_text.text == "asli"
    assert original_rpr.find(W_I) is None


def test_copy_rpr_is_deep_copy() -> None:
    rpr = _rpr()
    bold = etree.SubElement(rpr, W_B)
    bold.set(W_VAL, "0")

    copied = copy_rpr(rpr)

    copied_bold = copied.find(W_B)
    assert copied is not rpr
    assert copied.getparent() is None
    assert copied_bold is not None
    assert copied_bold is not bold
    assert copied_bold.get(W_VAL) == "0"

    copied_bold.set(W_VAL, "1")
    copied.append(etree.Element(W_I))
    assert bold.get(W_VAL) == "0"
    assert rpr.find(W_I) is None


def test_strip_bold_removes_active_toggles_and_counts_them() -> None:
    rpr = _rpr()
    etree.SubElement(rpr, W_B)
    etree.SubElement(rpr, W_BCS)
    inactive = etree.SubElement(rpr, W_B)
    inactive.set(W_VAL, "0")
    italic = etree.SubElement(rpr, W_I)

    removed = strip_bold_from_rpr(rpr)

    assert removed == 2
    assert rpr.findall(W_B) == [inactive]
    assert rpr.findall(W_BCS) == []
    assert rpr.find(W_I) is italic


@pytest.mark.parametrize("value", ["0", "false", "off", "none", "no", "False", " off "])
def test_strip_bold_keeps_inactive_values(value: str) -> None:
    rpr = _rpr()
    for tag in (W_B, W_BCS):
        element = etree.SubElement(rpr, tag)
        element.set(W_VAL, value)

    assert strip_bold_from_rpr(rpr) == 0
    assert len(rpr) == 2


@pytest.mark.parametrize("value", ["1", "true", "on"])
def test_strip_bold_removes_active_values(value: str) -> None:
    rpr = _rpr()
    for tag in (W_B, W_BCS):
        element = etree.SubElement(rpr, tag)
        element.set(W_VAL, value)

    assert strip_bold_from_rpr(rpr) == 2
    assert len(rpr) == 0


def test_strip_bold_without_bold_returns_zero() -> None:
    rpr = _rpr()
    etree.SubElement(rpr, W_I)

    assert strip_bold_from_rpr(rpr) == 0
    assert len(rpr) == 1


def test_run_child_order_is_valid() -> None:
    paragraph = _paragraph()
    with_rpr = make_run(paragraph, text=" teks ", rpr=_rpr())
    appended = append_text_run(paragraph, "x", rpr=_rpr())

    for run in (with_rpr, appended):
        tags = [child.tag for child in run]
        assert tags.index(W_RPR) < tags.index(W_T)
