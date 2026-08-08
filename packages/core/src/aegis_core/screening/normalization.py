"""Türkçe ad normalizasyonu — tarama doğruluğunun temel taşı (E1.3).

Tarama motoruna giden **sorgu** ile veri kümesindeki **kayıt**, karşılaştırılmadan önce
tam olarak bu modülden geçer. Türkçe'ye özgü üç tuzak burada kapatılır:

1. **İ/ı ikilisi.** Python'un ``str.lower()``'ı Türkçe bilmez: ``"I".lower() == "i"``
   (doğrusu ``"ı"``) ve ``"İ".lower()`` iki kod noktalı ``"i̇"`` üretir (i + birleşik
   nokta). ``ISTANBUL`` ile ``İSTANBUL`` sessizce farklı normalleşirse yaptırım listesi
   eşleşmesi **kaçar** — yanlış negatif, bu üründeki tehlikeli hata türü.
2. **Harf çevirisi (transliterasyon).** Uluslararası listeler Türkçe adları çoğu zaman
   ASCII yazar (``Şahin`` → ``Sahin``, ``Çağlar`` → ``Caglar``). Kanonik biçimin yanında
   bir de ASCII biçim üretilir; eşleştirme ikisini de dener.
3. **Tüzel-kişilik ekleri.** ``A.Ş.``, ``Ltd. Şti.``, ``San. ve Tic.`` gibi ekler ayırt
   edici değildir ama skoru düşürür. Sondan başlayarak, en uzun eşleşme önce olmak üzere
   yinelemeli temizlenir; ad tamamen boşalacaksa temizleme durur.

Kişi adlarında tüzel ek temizliği yapılmaz; yalnız unvan önekleri (``Dr.``, ``Av.``)
atılır.

**Ek eşleştirmesi ASCII üzerinden yapılır.** Böylece "Ltd. Şti." ve "LTD STI" tek bir
tablo girdisiyle yakalanır; her ekin iki imlasını ayrı ayrı listeleme zorunluluğu (ve
birini unutunca doğacak sessiz yanlış negatif) ortadan kalkar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

# ── Türkçe büyük/küçük harf eşlemeleri ───────────────────────────────────────
# Küçültmeden ÖNCE uygulanır; ardından str.lower() kalan (ASCII/Latin) harfleri çevirir.
_LOWER_PRE = str.maketrans({"I": "ı", "İ": "i"})
_UPPER_PRE = str.maketrans({"i": "İ", "ı": "I"})

# Kanonik biçimden ASCII biçime harf çevirisi (küçük harf üzerinde çalışır).
_ASCII_FOLD = str.maketrans(
    {
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "ç": "c",
        "â": "a",
        "î": "i",
        "û": "u",
        "ê": "e",
        "ô": "o",
    }
)

# Harf/rakam olmayan her şey ayraçtır: "A.Ş." → "a ş", "ABC-DEF" → "abc def".
# ``\W`` Unicode-duyarlıdır (aksanlı harfler korunur); alt çizgi ayrıca ayraç sayılır.
_NON_ALNUM = re.compile(r"[\W_]+", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


class SubjectType(StrEnum):
    """Taranan öznenin türü — normalizasyon kuralları buna göre değişir."""

    PERSON = "person"
    COMPANY = "company"


def turkish_lower(text: str) -> str:
    """Türkçe-doğru küçük harfe çevirir (``I`` → ``ı``, ``İ`` → ``i``).

    Önce Türkçe'ye özgü iki harf elle eşlenir, sonra ``str.lower()`` kalanı çevirir.
    Bu sıra şarttır: ``"İ".lower()`` doğrudan çağrılırsa birleşik noktalı ``i̇`` üretir.
    """
    return text.translate(_LOWER_PRE).lower()


def turkish_upper(text: str) -> str:
    """Türkçe-doğru büyük harfe çevirir (``i`` → ``İ``, ``ı`` → ``I``)."""
    return text.translate(_UPPER_PRE).upper()


def to_ascii(text: str) -> str:
    """Türkçe küçük harfleri ASCII karşılıklarına çevirir (``şahin`` → ``sahin``).

    Eşlemede olmayan aksanlı harfler için NFKD ayrıştırma + birleşik işaret atma
    yedeği çalışır; böylece yabancı kaynaklı adlar (``José``) da ASCII'ye iner.
    """
    folded = text.translate(_ASCII_FOLD)
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def canonicalize(text: str) -> str:
    """Boşluk/noktalama kanonikleştirir ve Türkçe-doğru küçültür (ek temizliği YOK).

    Unicode NFC ile başlanır: aynı harfin önceden-birleşik ve ayrık yazımı (ör. ``ü``
    tek kod noktası vs ``u`` + iki nokta) aynı sonuca inmelidir.
    """
    normalized = unicodedata.normalize("NFC", text)
    lowered = turkish_lower(normalized)
    spaced = _NON_ALNUM.sub(" ", lowered)
    return _WHITESPACE.sub(" ", spaced).strip()


def _fold_phrases(phrases: tuple[tuple[str, ...], ...]) -> tuple[tuple[str, ...], ...]:
    """Ek tablosunu ASCII'ye indirger, uzun ifade önce gelecek şekilde sıralar.

    Uzunluğa göre azalan sıralama şarttır: ``("sanayi","ve","ticaret")`` tek başına
    ``("ticaret",)`` tarafından parça parça yenmemelidir. Eşit uzunlukta alfabetik
    sıra, sonucu koşudan koşuya deterministik tutar.
    """
    folded = {tuple(to_ascii(token) for token in phrase) for phrase in phrases}
    return tuple(sorted(folded, key=lambda phrase: (-len(phrase), phrase)))


# ── Tüzel-kişilik ekleri (noktalama temizlendikten sonraki token dizileri) ───
# "A.Ş." → ("a", "ş"). Tablo Türkçe imlayla yazılır; ``_fold_phrases`` ASCII karşılığını
# da kapsayacak biçimde indirger.
_LEGAL_FORM_PHRASES: tuple[tuple[str, ...], ...] = (
    # Anonim / limited şirket biçimleri
    ("türk", "anonim", "şirketi"),
    ("anonim", "şirketi"),
    ("anonim", "ortaklığı"),
    ("anonim", "şti"),
    ("limited", "şirketi"),
    ("limited", "şti"),
    ("ltd", "şirketi"),
    ("ltd", "şti"),
    ("t", "a", "ş"),
    ("a", "ş"),
    ("a", "o"),
    ("aş",),
    ("ltd",),
    ("limited",),
    ("şirketi",),
    ("şti",),
    # Şahıs/ortaklık biçimleri
    ("kollektif", "şirketi"),
    ("koll", "şti"),
    ("komandit", "şirketi"),
    ("kom", "şti"),
    ("adi", "ortaklık"),
    ("iktisadi", "işletmesi"),
    # Faaliyet eki kalıpları (ayırt edici değil, skoru bozar)
    ("iç", "ve", "dış", "ticaret"),
    ("sanayi", "ve", "ticaret"),
    ("ticaret", "ve", "sanayi"),
    ("san", "ve", "tic"),
    ("tic", "ve", "san"),
    ("sanayi", "ticaret"),
    ("san", "tic"),
    ("dış", "ticaret"),
    ("dış", "tic"),
    ("ithalat", "ihracat"),
    ("ith", "ihr"),
    ("sanayi",),
    ("ticaret",),
    ("san",),
    ("tic",),
    ("ithalat",),
    ("ihracat",),
    ("pazarlama",),
    ("paz",),
    # Şube ekleri
    ("şubesi",),
    ("şube",),
    ("şb",),
    # Ek temizlendikten sonra sonda kalabilen bağlaç
    ("ve",),
)

# Yalnız **tüzel kişilik türünü** bildiren, hiçbir bağlamda ayırt edici olmayan ekler.
# Bunlar adın ortasında da temizlenir: "ABC Lojistik A.Ş. İstanbul Şubesi" ile
# "ABC Lojistik İstanbul Şubesi" aynı ada inmelidir. Sektör kelimeleri (ticaret,
# sanayi …) bu listeye ALINMAZ — "Ticaret Bankası"nda "ticaret" ayırt edicidir ve
# yalnız sondayken atılır.
_ENTITY_FORM_PHRASES: tuple[tuple[str, ...], ...] = (
    ("türk", "anonim", "şirketi"),
    ("anonim", "şirketi"),
    ("anonim", "ortaklığı"),
    ("anonim", "şti"),
    ("limited", "şirketi"),
    ("limited", "şti"),
    ("ltd", "şirketi"),
    ("ltd", "şti"),
    ("kollektif", "şirketi"),
    ("komandit", "şirketi"),
    ("koll", "şti"),
    ("kom", "şti"),
    ("t", "a", "ş"),
    ("a", "ş"),
    ("a", "o"),
    ("aş",),
    ("ltd",),
    ("şti",),
)

# Şirket unvanlarında ayırt edici olmayan bağlaç. "Demir ve Çelik" ile "Demir & Çelik"
# aynı ada inmelidir; "&" zaten noktalama olarak düşer, "ve" burada düşer. Kişi
# adlarında uygulanmaz.
_COMPANY_STOPWORDS: frozenset[str] = frozenset({"ve"})

# Kişi adlarında atılan unvan önekleri.
_PERSON_TITLES: frozenset[str] = frozenset(
    {"dr", "doç", "prof", "av", "sn", "bay", "bayan", "mr", "mrs", "ms", "sayın"}
)

# Çalışma zamanında kullanılan (ASCII'ye indirgenmiş) tablolar.
_LEGAL_FORMS_FOLDED = _fold_phrases(_LEGAL_FORM_PHRASES)
_ENTITY_FORMS_FOLDED = _fold_phrases(_ENTITY_FORM_PHRASES)
_COMPANY_STOPWORDS_FOLDED = frozenset(to_ascii(word) for word in _COMPANY_STOPWORDS)
_PERSON_TITLES_FOLDED = frozenset(to_ascii(title) for title in _PERSON_TITLES)


def _strip_trailing_legal_forms(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Sondaki tüzel-kişilik/faaliyet eklerini yinelemeli temizler (uzun ifade önce).

    Ad tamamen boşalacaksa temizleme durur: "Sanayi A.Ş." gibi bir unvan, ayırt edici
    hiçbir token'ı kalmayacak şekilde silinmemelidir.
    """
    remaining = list(tokens)
    folded = [to_ascii(token) for token in remaining]
    stripped: list[str] = []
    changed = True
    while changed and remaining:
        changed = False
        for phrase in _LEGAL_FORMS_FOLDED:
            size = len(phrase)
            if size >= len(remaining):
                # Eşitlik dahil: geriye en az bir ayırt edici token kalmalı.
                continue
            if tuple(folded[-size:]) == phrase:
                stripped.insert(0, " ".join(remaining[-size:]))
                del remaining[-size:]
                del folded[-size:]
                changed = True
                break
    return remaining, stripped


def _strip_inner_entity_forms(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Adın **ortasındaki** tüzel-kişilik eklerini temizler ("… A.Ş. İstanbul Şubesi").

    Yalnız ``_ENTITY_FORM_PHRASES`` (saf tüzel biçim) uygulanır; sektör kelimeleri
    gövdenin ortasında ayırt edici olabileceği için dokunulmaz.
    """
    remaining = list(tokens)
    folded = [to_ascii(token) for token in remaining]
    stripped: list[str] = []
    changed = True
    while changed and len(remaining) > 1:
        changed = False
        for phrase in _ENTITY_FORMS_FOLDED:
            size = len(phrase)
            if size >= len(remaining):
                continue
            for start in range(len(remaining) - size + 1):
                if tuple(folded[start : start + size]) == phrase:
                    stripped.append(" ".join(remaining[start : start + size]))
                    del remaining[start : start + size]
                    del folded[start : start + size]
                    changed = True
                    break
            if changed:
                break
    return remaining, stripped


def _drop_company_stopwords(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Ayırt edici olmayan bağlaçları atar; hepsi atılacaksa dokunmaz."""
    kept = [token for token in tokens if to_ascii(token) not in _COMPANY_STOPWORDS_FOLDED]
    if not kept:
        return tokens, []
    dropped = [token for token in tokens if to_ascii(token) in _COMPANY_STOPWORDS_FOLDED]
    return kept, dropped


def _strip_legal_forms(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Şirket adı temizliğinin tamamı: sondan ekler → gövdedeki tüzel biçim → bağlaçlar."""
    remaining, stripped = _strip_trailing_legal_forms(tokens)
    remaining, inner = _strip_inner_entity_forms(remaining)
    remaining, stopwords = _drop_company_stopwords(remaining)
    return remaining, stripped + inner + stopwords


def _strip_person_titles(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Baştaki unvan öneklerini (``dr``, ``av`` …) atar; ad boşalacaksa dokunmaz."""
    remaining = list(tokens)
    stripped: list[str] = []
    while len(remaining) > 1 and to_ascii(remaining[0]) in _PERSON_TITLES_FOLDED:
        stripped.append(remaining.pop(0))
    return remaining, stripped


@dataclass(frozen=True)
class NormalizedName:
    """Bir adın normalizasyon çıktısı — eşleştirmenin tüm biçimleri tek yerde."""

    original: str
    """Kullanıcının girdiği ham metin (kanıt/denetim için korunur)."""

    canonical: str
    """Türkçe-doğru küçültülmüş, noktalama sadeleşmiş, ekleri atılmış biçim."""

    ascii: str
    """``canonical``ın ASCII harf çevirisi (uluslararası listelerle eşleşme için)."""

    tokens: tuple[str, ...]
    """``canonical``ın kelimeleri (sırayla)."""

    stripped: tuple[str, ...]
    """Atılan tüzel-kişilik ekleri / unvanlar — neden eşleştiğinin açıklaması."""

    subject_type: SubjectType
    """Normalizasyonun hangi kural setiyle yapıldığı."""

    @property
    def sort_key(self) -> str:
        """Kelime sırasından bağımsız karşılaştırma anahtarı (``ascii`` üzerinden).

        ``"Ahmet Yılmaz"`` ile ``"YILMAZ, Ahmet"`` aynı anahtara iner; ad-soyad sırası
        listeden listeye değiştiği için değerlendirme setinde denklik ölçüsü budur.
        """
        return " ".join(sorted(self.ascii.split()))

    @property
    def is_empty(self) -> bool:
        """Normalizasyon sonrası ayırt edici hiçbir şey kalmadı mı."""
        return not self.canonical


def normalize_name(
    name: str, subject_type: SubjectType | str = SubjectType.COMPANY
) -> NormalizedName:
    """Bir adı tarama için kanonikleştirir.

    Şirketlerde tüzel-kişilik ekleri, kişilerde unvan önekleri atılır. Sorgu tarafı ile
    veri kümesi tarafı **aynı** çağrıyı kullanmalıdır; aksi hâlde iki taraf farklı
    kanonik uzaya düşer ve eşleşme kaçar.
    """
    resolved_type = SubjectType(subject_type)
    tokens = canonicalize(name).split()
    if resolved_type is SubjectType.COMPANY:
        kept, stripped = _strip_legal_forms(tokens)
    else:
        kept, stripped = _strip_person_titles(tokens)
    canonical = " ".join(kept)
    return NormalizedName(
        original=name,
        canonical=canonical,
        ascii=to_ascii(canonical),
        tokens=tuple(kept),
        stripped=tuple(stripped),
        subject_type=resolved_type,
    )


def name_variants(normalized: NormalizedName) -> tuple[str, ...]:
    """Tarama motoruna gönderilecek ad varyantları (tekilleştirilmiş, boşlar atılmış).

    Kanonik biçim ile ASCII biçim çoğu Türkçe adda farklıdır (``şahin`` / ``sahin``);
    ikisi de sorgulanır ki liste hangi imlayı kullanırsa kullansın eşleşme yakalansın.
    Ham girdi de eklenir: yente'nin kendi analizörü bazı durumlarda ham metinde daha
    iyi sonuç verir ve fazladan varyant **yanlış negatif riskini** düşürür.
    """
    candidates = (normalized.canonical, normalized.ascii, normalized.original.strip())
    seen: dict[str, None] = {}
    for candidate in candidates:
        if candidate:
            seen.setdefault(candidate, None)
    return tuple(seen)
