"""MASAK dondurma listesi → FtM dönüşümü testleri (E1.3).

En kritik iddia: **varlık kimliği kararlıdır**. Kimlik her yenilemede değişseydi,
onaylanmış/elenmiş eşleşmelerin bağı kopar ve incelenmiş bir kayıt ertesi gün yeniden
"bekliyor" olarak karşımıza çıkardı.
"""

from __future__ import annotations

import json
from pathlib import Path

from aegis_core.screening.masak import (
    SANCTION_TOPIC,
    build_dataset_file,
    normalize_identifier,
    parse_csv,
    to_ftm_entities,
)
from aegis_core.screening.normalization import SubjectType

CSV_ORNEK = """Adı Soyadı;Tür;Doğum Tarihi;Uyruğu;Pasaport No;Karar No;Dayanak
Şahin Öztürk;Gerçek Kişi;1975-04-12;TR;U12345678;2024/8123;6415 s.K. 7. madde
Yıldız İnşaat San. ve Tic. Ltd. Şti.;Tüzel Kişi;;TR;;2024/8124;6415 s.K. 7. madde
;Gerçek Kişi;;;;;
"""


def test_csv_ayrilir_ve_adsiz_satir_atlanir() -> None:
    records = parse_csv(CSV_ORNEK)
    assert len(records) == 2
    assert records[0].name == "Şahin Öztürk"
    assert records[0].birth_date == "1975-04-12"
    assert records[0].decision_number == "2024/8123"


def test_kayit_turu_sutundan_okunur() -> None:
    records = parse_csv(CSV_ORNEK)
    assert records[0].record_type is SubjectType.PERSON
    assert records[1].record_type is SubjectType.COMPANY


def test_kayit_turu_sutun_yoksa_unvandan_cikarilir() -> None:
    """Tür sütunu yoksa tüzel ek taşıyan ad şirket, taşımayan kişi kabul edilir."""
    records = parse_csv("Adı Soyadı\nABC Yapı A.Ş.\nAhmet Yılmaz\n")
    assert records[0].record_type is SubjectType.COMPANY
    assert records[1].record_type is SubjectType.PERSON


def test_ftm_varliklari_yaptirim_konusu_tasir() -> None:
    entities = to_ftm_entities(parse_csv(CSV_ORNEK), source_url="https://masak.example/karar")
    assert len(entities) == 2
    for entity in entities:
        assert entity["properties"]["topics"] == [SANCTION_TOPIC]
        assert entity["properties"]["sourceUrl"] == ["https://masak.example/karar"]
        assert entity["datasets"] == ["masak_dondurma"]


def test_ftm_semasi_kayit_turune_gore_secilir() -> None:
    entities = to_ftm_entities(parse_csv(CSV_ORNEK))
    schemas = {entity["properties"]["name"][0]: entity["schema"] for entity in entities}
    assert schemas["Şahin Öztürk"] == "Person"
    assert schemas["Yıldız İnşaat San. ve Tic. Ltd. Şti."] == "Company"


def test_takma_adlar_kanonik_ve_ascii_bicimleri_icerir() -> None:
    """Liste "ŞAHİN" yazarken kullanıcı "Sahin" arayabilir — ikisi de eşleşmeli."""
    entity = to_ftm_entities(parse_csv(CSV_ORNEK))[0]
    aliases = entity["properties"]["alias"]
    assert "sahin ozturk" in aliases
    assert "şahin öztürk" in aliases


def test_varlik_kimligi_kararlidir() -> None:
    """Aynı girdi iki kez işlenirse aynı kimlik çıkmalıdır (karar bağı kopmasın)."""
    first = to_ftm_entities(parse_csv(CSV_ORNEK))
    second = to_ftm_entities(parse_csv(CSV_ORNEK))
    assert [entity["id"] for entity in first] == [entity["id"] for entity in second]


def test_varlik_kimligi_ad_sirasindan_etkilenmez() -> None:
    """Kaynak "Öztürk, Şahin" yazarsa da aynı kayıt aynı kimliği almalıdır."""
    duz = to_ftm_entities(parse_csv("Adı Soyadı;Karar No\nŞahin Öztürk;2024/1\n"))
    ters = to_ftm_entities(parse_csv("Adı Soyadı;Karar No\nÖztürk, Şahin;2024/1\n"))
    assert duz[0]["id"] == ters[0]["id"]


def test_farkli_kayitlar_farkli_kimlik_alir() -> None:
    entities = to_ftm_entities(parse_csv(CSV_ORNEK))
    assert entities[0]["id"] != entities[1]["id"]


def test_tekrarli_kayitlar_teklenir() -> None:
    csv_text = "Adı Soyadı;Karar No\nŞahin Öztürk;2024/1\nŞahin Öztürk;2024/1\n"
    assert len(to_ftm_entities(parse_csv(csv_text))) == 1


def test_tanınmayan_sutunlar_kaybolmaz() -> None:
    records = parse_csv("Adı Soyadı;Bilinmeyen Sütun\nAhmet Yılmaz;değer\n")
    assert records[0].extra == {"Bilinmeyen Sütun": "değer"}


def test_program_etiketi_karar_bilgisini_tasir() -> None:
    entity = to_ftm_entities(parse_csv(CSV_ORNEK))[0]
    program = entity["properties"]["program"][0]
    assert "6415" in program
    assert "2024/8123" in program


def test_dosya_yazimi_json_lines_uretir(tmp_path: Path) -> None:
    destination = tmp_path / "masak" / "entities.ftm.json"
    written = build_dataset_file(CSV_ORNEK, destination, source_url="https://masak.example")
    assert written == 2
    lines = destination.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert all("id" in entity and "schema" in entity for entity in parsed)
    # Geçici dosya arkada bırakılmamalı (atomik yazım).
    assert not list(destination.parent.glob("*.tmp"))


def test_dosya_yazimi_ustune_yazar(tmp_path: Path) -> None:
    destination = tmp_path / "entities.ftm.json"
    build_dataset_file(CSV_ORNEK, destination)
    build_dataset_file("Adı Soyadı\nTek Kayıt\n", destination)
    assert len(destination.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_normalize_identifier_yalniz_rakam_birakir() -> None:
    assert normalize_identifier("123 456 78-90") == "1234567890"
    assert normalize_identifier("TR-1234567890") == "1234567890"
