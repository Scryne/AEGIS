"""Toplu tarama CSV çekirdeği (E3.3)."""

from __future__ import annotations

import pytest

from aegis_core.batch import csv_import
from aegis_core.batch.csv_import import CsvImportError
from aegis_core.batch.service import export_csv, risk_rank


def _csv(text: str, encoding: str = "utf-8") -> bytes:
    return text.replace("\n", "\r\n").encode(encoding)


def test_excel_turkish_semicolon_cp1254_is_read() -> None:
    data = _csv("Ticaret Unvanı;Vergi No;Tür\nYıldız İnşaat A.Ş.;1234567890;şirket\n", "cp1254")
    parsed = csv_import.parse(data)
    assert parsed.delimiter == ";"
    assert parsed.headers == ["Ticaret Unvanı", "Vergi No", "Tür"]
    assert parsed.rows[0][0] == "Yıldız İnşaat A.Ş."


def test_utf8_bom_and_comma() -> None:
    parsed = csv_import.parse("﻿name,country\nAcme Ltd,GB\n".encode())
    assert parsed.headers == ["name", "country"]
    assert parsed.delimiter == ","


def test_mapping_suggestion_from_turkish_and_english_headers() -> None:
    m = csv_import.suggest_mapping(["Müşteri No", "Ad Soyad", "VKN", "Ülke", "Tip"])
    assert m == {
        "name": "Ad Soyad",
        "schema_type": "Tip",
        "tax_number": "VKN",
        "mersis_number": None,
        "country": "Ülke",
        "external_ref": "Müşteri No",
    }


def test_national_id_column_is_refused() -> None:
    headers = ["Ad", "TCKN"]
    assert csv_import.national_id_headers(headers) == ["TCKN"]
    with pytest.raises(CsvImportError, match="TCKN"):
        csv_import.validate_mapping(headers, {"name": "Ad", "external_ref": "TCKN"})


def test_mapping_requires_name_and_distinct_columns() -> None:
    with pytest.raises(CsvImportError, match="Ad / unvan"):
        csv_import.validate_mapping(["A", "B"], {"tax_number": "A"})
    with pytest.raises(CsvImportError, match="iki alana"):
        csv_import.validate_mapping(["A", "B"], {"name": "A", "external_ref": "A"})
    with pytest.raises(CsvImportError, match="dosyada yok"):
        csv_import.validate_mapping(["A"], {"name": "Z"})


def test_rows_validation_types_and_in_file_duplicates() -> None:
    parsed = csv_import.parse(
        _csv(
            "Ad;Tür;Vergi No\n"
            "Yıldız İnşaat A.Ş.;şirket;1234567890\n"
            ";şirket;\n"
            "Ayşe Demir;kişi;\n"
            "Yildiz Insaat AS;Şirket;1234567890\n"
            "Ayşe  Demir;gerçek kişi;\n"
            "Belirsiz Tür Ltd;vakıf;\n"
        )
    )
    rows = csv_import.build_rows(
        parsed, {"name": "Ad", "schema_type": "Tür", "tax_number": "Vergi No"}
    )
    assert [r.row_no for r in rows] == [2, 3, 4, 5, 6, 7]
    assert rows[0].valid
    assert rows[0].data["schema_type"] == "Company"
    assert rows[1].errors == ["Ad / unvan boş."]
    assert rows[2].data["schema_type"] == "Person"
    assert rows[3].duplicate_of == 2  # aynı vergi no
    assert rows[4].duplicate_of == 4  # aynı normalize ad + tür (boşluk farkı)
    assert rows[4].data["name"] == "Ayşe Demir"
    assert not rows[5].valid
    assert "Tür anlaşılamadı" in rows[5].errors[0]


def test_bad_tax_number_is_warning_not_error() -> None:
    parsed = csv_import.parse(_csv("Ad;VKN\nAcme;12345\n"))
    (row,) = csv_import.build_rows(parsed, {"name": "Ad", "tax_number": "VKN"})
    assert row.valid
    assert row.warnings
    assert "10 haneli" in row.warnings[0]


def test_limits() -> None:
    with pytest.raises(CsvImportError, match="satır"):
        csv_import.parse(_csv("Ad\n" + "x\n" * (csv_import.MAX_ROWS + 1)))
    with pytest.raises(CsvImportError, match="sınırını"):
        csv_import.decode(b"a" * (csv_import.MAX_BYTES + 1))
    with pytest.raises(CsvImportError, match="satır yok"):
        csv_import.parse(_csv("Ad\n"))
    with pytest.raises(CsvImportError, match="aynı adlı"):
        csv_import.parse(_csv("Ad;ad\nx;y\n"))


def test_risk_rank_orders_sanction_over_pep_over_score() -> None:
    sanction = risk_rank(sanction_hits=1, pep_hits=0, flagged=0, top_score=0.5)
    pep = risk_rank(sanction_hits=0, pep_hits=1, flagged=1, top_score=0.99)
    flagged = risk_rank(sanction_hits=0, pep_hits=0, flagged=1, top_score=0.9)
    clean = risk_rank(sanction_hits=0, pep_hits=0, flagged=0, top_score=None)
    assert sanction > pep > flagged > clean == 0


def test_export_neutralises_formula_cells() -> None:
    from aegis_core.models import ScreeningBatchRow

    row = ScreeningBatchRow(
        row_no=2,
        data={"name": "=HYPERLINK(1)", "schema_type": "Company", "external_ref": "+90"},
        errors=[],
        warnings=[],
        status="done",
    )
    text = export_csv([row]).decode("utf-8")
    assert text.startswith("﻿Satır;")
    assert "'=HYPERLINK(1)" in text
    assert "'+90" in text
