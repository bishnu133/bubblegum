"""Feature: click a control inside a NAMED table column's header.

Several column headers often carry the same filter / search / sort icon, so an
unscoped "Click the Search icon" lands on whichever comes first. Naming the
column ("… of the Title column") now pins the control inside that header —
generically (Ant, plain HTML, inside a modal), with no selector.

Runs against a real browser; skips when none is available. Set
``BG_CHROMIUM_EXECUTABLE`` to point at a Chromium binary if needed.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

_SEARCH = ('<svg viewBox="64 64 896 896" data-icon="search" width="1em" height="1em" '
           'aria-hidden="true"><path d="M909 854"></path></svg>')
_FILTER = ('<svg viewBox="64 64 896 896" data-icon="filter" width="1em" height="1em" '
           'aria-hidden="true"><path d="M349 838"></path></svg>')
_CARET = ('<svg viewBox="0 0 1024 1024" data-icon="caret-up" width="1em" height="1em" '
          'aria-hidden="true"><path d="M858 625"></path></svg>')


def _trig(col, icon, svg):
    return (f'<span role="button" tabindex="-1" class="ant-dropdown-trigger ant-table-filter-trigger" '
            f'data-col="{col}"><span role="img" aria-label="{icon}" class="anticon anticon-{icon}">{svg}</span></span>')


def _th(title, trig):
    return (f'<th class="ant-table-cell" scope="col"><div class="ant-table-filter-column">'
            f'<span class="ant-table-column-title">{title}</span>{trig}</div></th>')


def _th_sort(title):
    return (f'<th class="ant-table-cell ant-table-column-has-sorters" scope="col">'
            f'<div class="ant-table-column-sorters"><span class="ant-table-column-title">{title}</span>'
            f'<span class="ant-table-column-sorter" data-col="{title}"><span role="img" aria-label="caret-up" '
            f'class="anticon anticon-caret-up">{_CARET}</span></span></div></th>')


_CLICK_LOG = """<script>window.__clicks=[];
document.querySelectorAll('[data-col]').forEach(el=>el.addEventListener('click',e=>{e.stopPropagation();
 window.__clicks.push(el.getAttribute('data-col')+':'+((el.querySelector('[aria-label]')||el).getAttribute('aria-label')));}));
(document.getElementById('topSearch')||{addEventListener(){}}).addEventListener('click',()=>window.__clicks.push('TOP'));
</script>"""

# Ant-style: page-level "Search" button + two column search triggers + two funnels + a sorter.
_ANT = f"""<!doctype html><html><body>
<button type="button" class="ant-btn" id="topSearch"><span>Search</span></button>
<table><thead class="ant-table-thead"><tr>
 {_th('Title', _trig('Title', 'search', _SEARCH))}{_th('Status', _trig('Status', 'filter', _FILTER))}
 {_th('Division', _trig('Division', 'filter', _FILTER))}{_th('Updated By', _trig('Updated By', 'search', _SEARCH))}
 {_th_sort('Start')}
</tr></thead><tbody><tr><td>a</td><td>Live</td><td>d</td><td>u</td><td>s</td></tr></tbody></table>
{_CLICK_LOG}</body></html>"""

# Plain HTML (no component library): header buttons named only by aria-label.
_PLAIN = """<!doctype html><html><body><table><thead><tr>
 <th>Name <button data-col="Name" aria-label="Search names">&#128269;</button></th>
 <th>Email <button data-col="Email" aria-label="Search emails">&#128269;</button></th>
 <th>Role <button data-col="Role" aria-label="Filter roles">&#9662;</button></th>
</tr></thead><tbody><tr><td>x</td><td>y</td><td>z</td></tr></tbody></table>""" + _CLICK_LOG + "</body></html>"

# A table inside an open modal shares column names with the table behind it.
_MODAL = f"""<!doctype html><html><body>
<table><thead><tr>{_th('Title', _trig('BG-Title', 'search', _SEARCH))}</tr></thead></table>
<div class="ant-modal-root"><div class="ant-modal-mask"></div><div class="ant-modal-wrap">
 <div role="dialog" aria-modal="true" class="ant-modal" style="z-index:1000"><div class="ant-modal-content">
 <table><thead><tr>{_th('Title', _trig('MODAL-Title', 'search', _SEARCH))}</tr></thead></table>
</div></div></div></div>{_CLICK_LOG}</body></html>"""


async def _clicks(html, step):
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import act, configure_runtime

    configure_runtime()
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    async with aw.async_playwright() as p:
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"No usable Chromium binary: {exc}")
        try:
            page = await browser.new_page()
            await page.set_content(html)
            res = await act(step, channel="web", page=page)
            return res, await page.evaluate("window.__clicks")
        finally:
            await browser.close()


@pytest.mark.parametrize(
    "step,expected",
    [
        ("Click on the Search icon of Title Column", ["Title:search"]),
        ("Click on the Search icon of Updated By Column", ["Updated By:search"]),
        ("Click the filter icon in the Division column", ["Division:filter"]),
        ("Click the Status column's filter icon", ["Status:filter"]),
        ("Click the sort icon of Start column", ["Start:caret-up"]),
    ],
)
async def test_ant_column_scoped_header_control(step, expected):
    res, clicks = await _clicks(_ANT, step)
    assert res.status == "passed", res.error
    assert clicks == expected
    assert res.target.resolver_name == "column_header_dom"


async def test_unscoped_search_button_unchanged():
    # Not column-scoped: the column-header resolver must not claim it.
    res, clicks = await _clicks(_ANT, "Click the Search button")
    assert res.status == "passed"
    assert clicks == ["TOP"]
    assert res.target.resolver_name != "column_header_dom"


@pytest.mark.parametrize(
    "step,expected",
    [
        ("Click the search icon of the Email column", ["Email:Search emails"]),
        ("Click the search icon of the Name column", ["Name:Search names"]),
        ("Click the filter icon in the Role column", ["Role:Filter roles"]),
    ],
)
async def test_plain_html_table_header_control(step, expected):
    res, clicks = await _clicks(_PLAIN, step)
    assert res.status == "passed", res.error
    assert clicks == expected


async def test_prefers_table_inside_open_modal():
    res, clicks = await _clicks(_MODAL, "Click the Search icon of the Title column")
    assert res.status == "passed", res.error
    assert clicks == ["MODAL-Title:search"]
