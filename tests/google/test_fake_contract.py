"""Test kontrak fake Drive/Slides/Sheets tanpa jaringan."""

from collections.abc import Callable

import pytest

from autooffice.google import FakeGoogleError
from autooffice.google.drive import DriveApi
from autooffice.google.fake import FakeGoogleServices
from autooffice.google.sheets import SheetsApi
from autooffice.google.slides import (
    PresentationSnapshot,
    SlidesApi,
    delete_text_request,
    insert_text_request,
)


def test_fakes_satisfy_domain_protocols() -> None:
    fake = FakeGoogleServices.create()

    assert isinstance(fake.drive, DriveApi)
    assert isinstance(fake.sheets, SheetsApi)
    assert isinstance(fake.slides, SlidesApi)


def test_fake_text_mutation_roundtrip(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake = FakeGoogleServices.create()
    fake.slides.add_presentation(make_snapshot(presentation_id="presentation-1"))

    fake.slides.batch_update(
        "presentation-1",
        [
            delete_text_request("shape-s01-title", cell_location=None),
            insert_text_request("shape-s01-title", "Teks baru", cell_location=None),
        ],
    )

    snapshot = fake.slides.get_presentation("presentation-1")
    title = next(
        element for element in snapshot.elements() if element.object_id == "shape-s01-title"
    )
    assert title.text == "Teks baru"
    assert snapshot.revision_id is not None


def test_fake_table_cell_mutation(make_snapshot: Callable[..., PresentationSnapshot]) -> None:
    fake = FakeGoogleServices.create()
    fake.slides.add_presentation(make_snapshot(presentation_id="presentation-1"))

    fake.slides.batch_update(
        "presentation-1",
        [
            delete_text_request("table-s01-table1", cell_location=(1, 0)),
            insert_text_request("table-s01-table1", "Peserta baru", cell_location=(1, 0)),
        ],
    )

    snapshot = fake.slides.get_presentation("presentation-1")
    table = next(element for element in snapshot.elements() if element.kind == "table")
    assert table.cells[1][0] == "Peserta baru"


def test_create_table_request_is_traced_and_rejected(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake = FakeGoogleServices.create()
    fake.slides.add_presentation(make_snapshot(presentation_id="presentation-1"))

    with pytest.raises(FakeGoogleError, match="CreateTableRequest"):
        fake.slides.batch_update(
            "presentation-1",
            [{"createTable": {"rows": 2, "columns": 2}}],
        )

    assert len(fake.slides.create_table_requests) == 1


def test_create_linked_chart_requires_existing_sheet_chart(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake = FakeGoogleServices.create()
    fake.slides.add_presentation(make_snapshot(presentation_id="presentation-1"))

    with pytest.raises(FakeGoogleError, match="tidak ada di spreadsheet"):
        fake.slides.batch_update(
            "presentation-1",
            [
                {
                    "createSheetsChart": {
                        "spreadsheetId": "missing",
                        "chartId": 1,
                        "linkingMode": "LINKED",
                        "elementProperties": {"pageObjectId": "slide-s02"},
                    }
                }
            ],
        )
