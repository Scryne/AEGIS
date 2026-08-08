"""Nesne deposu yardımcıları — saf kısımlar (E1.4).

Ağ gerektiren kısımlar (boto3 çağrıları) entegrasyon testlerinde taklit edilir; burada
anahtar üretimi ve dosya adı sadeleştirmesi sınanır. Bunlar küçük ama kritiktir: anahtar
şeması kiracı ayrımını görünür kılar ve bozuk bir dosya adı depoda erişilemez nesne
yaratabilir.
"""

from __future__ import annotations

import uuid

from aegis_core.documents.storage import build_storage_key, safe_filename, sha256_hex


def test_safe_filename_turkce_karakterleri_indirger() -> None:
    assert safe_filename("İmza Sirküleri (2024).pdf") == "Imza-Sirkuleri-2024-.pdf"


def test_safe_filename_bos_girdide_varsayilan_verir() -> None:
    assert safe_filename("///") == "belge"
    assert safe_filename("") == "belge"


def test_safe_filename_uzunlugu_sinirlar() -> None:
    assert len(safe_filename("a" * 500)) <= 120


def test_storage_key_kiraci_onekiyle_baslar() -> None:
    """Nesne deposunda RLS yoktur; kiracı ayrımı anahtarda görünür olmalıdır."""
    tenant_id = uuid.uuid4()
    document_id = uuid.uuid4()
    key = build_storage_key(tenant_id, document_id, "faaliyet belgesi.pdf")
    assert key.startswith(f"{tenant_id}/")
    assert str(document_id) in key
    assert key.endswith("faaliyet-belgesi.pdf")


def test_storage_key_belge_basina_tekildir() -> None:
    tenant_id = uuid.uuid4()
    first = build_storage_key(tenant_id, uuid.uuid4(), "ayni-ad.pdf")
    second = build_storage_key(tenant_id, uuid.uuid4(), "ayni-ad.pdf")
    assert first != second


def test_sha256_bilinen_deger() -> None:
    # Boş girdinin SHA-256'sı — bütünlük özetinin doğru algoritmadan geldiğinin çapası.
    assert sha256_hex(b"") == ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
