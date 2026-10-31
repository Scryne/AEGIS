"""ŞİB formunun resmî kod listeleri (E2.2, ADR-0011).

Kaynak (birincil, MASAK): *Şüpheli İşlem Bildirim Rehberi — Serbest Muhasebeci, Serbest
Muhasebeci Mali Müşavir ve Yeminli Mali Müşavirler*, MSK-RHB-ŞİB-018-1.0, 16.06.2025, §4.2
(form bölümleri A–G) ve *Şüphe Kategorileri Referans Tablosu* (SK-Kodlari.pdf, rehberin §4.2.6
atfıyla). Değerler bu iki belgeden harfiyen alınmıştır; MASAK Online ekranının alan bazlı
zorunlulukları herkese açık değildir, burada yalnız rehberde açıkça yazanlar uygulanır.

AEGIS'in çapa segmenti SM/SMMM/YMM'dir (ROADMAP §1). Diğer yükümlü gruplarının formları farklıdır
(ör. bankalarda hesap bölümü var); başka gruba açılırken rehberi ayrı bir sürüm olarak eklenir.
"""

from __future__ import annotations

from typing import Final

REHBER: Final = {
    "kod": "MSK-RHB-ŞİB-018-1.0",
    "ad": "Şüpheli İşlem Bildirim Rehberi (Serbest Muhasebeci, Serbest Muhasebeci Mali "
    "Müşavir ve Yeminli Mali Müşavirler)",
    "tarih": "16.06.2025",
    "url": "https://ms.hmb.gov.tr/uploads/sites/12/2025/06/SIB-REHBER-SM-MM-1.0-18c7f4499a2664a5.pdf",
    "sk_tablosu": "https://ms.hmb.gov.tr/uploads/sites/12/2024/10/SK-Kodlari.pdf",
}

# §4.2.7: "asgari 300 karakter girilmesi zorunlu olup … azami karakter sayısı 50.000".
ACIKLAMA_EN_AZ: Final = 300
ACIKLAMA_EN_COK: Final = 50_000
# §4.2.6: "en az biri ve en fazla üçü seçilerek".
SK_EN_AZ: Final = 1
SK_EN_COK: Final = 3

# (B) Bildirim kategorisi — "yalnızca bir tanesi işaretlenecektir".
KATEGORILER: Final = {
    "aklama": "Suç gelirlerinin aklanması",
    "teror": "Terörizmin finansmanı",
    "kis": "Kitle imha silahlarının yayılmasının finansmanı",
}
TEROR_ORGUT_TURLERI: Final = {
    "bolucu": "Bölücü Terör Örgütleri",
    "dini_istismar": "Dini İstismar Eden Terör Örgütleri",
    "asiri_sol": "Aşırı Sol Terör Örgütleri",
}
ACILIYET: Final = {
    "normal": "Normal",
    "ivedi": "İvedi",
    "cok_ivedi": "Çok İvedi",
    "erteleme_talepli": "İşlemin Ertelenmesi Talepli",
}
BILDIRIM_TURU: Final = {"yeni": "Yeni", "ek": "Ek"}

# (C) Gerçek kişinin işlemle bağlantısı.
GERCEK_BAGLANTI: Final = {
    "kendisi_adina": "Kendisi Adına İşlem Yapan",
    "baskasi_adina": "Başkası Adına İşlem Yapan",
    "adina_yapilan": "Adına İşlem Yapılan",
    "gercek_faydalanici": "Gerçek Faydalanıcı",
    "dolayli": "Dolaylı Olarak İlgili",
}
# (D) Tüzel/diğer kişinin bağlantısı.
TUZEL_BAGLANTI: Final = {
    "adina_yapilan": "Adına İşlem Yapılan",
    "dolayli": "Dolaylı Olarak İlgili",
}
KURULUS_NEVI: Final = {
    "ticaret_sicili": "Ticaret Siciline Kayıtlı Tüzel Kişiler",
    "yurt_disi": "Yurt dışında Yerleşik Tüzel Kişiler",
    "tuzel_kisiligi_olmayan": "Tüzel Kişiliği Olmayan Teşekküller",
    "guven_sozlesmesi": "Yurt Dışında Kurulmuş Güven Sözleşmeleri",
    "dernek": "Dernek",
    "vakif": "Vakıf",
    "siyasi_parti": "Siyasi Parti",
    "sendika": "Sendika, Federasyon, Konfederasyon",
}
KIMLIK_BELGELERI: Final = {
    "nufus_cuzdani": "Nüfus Cüzdanı No",
    "tc_kimlik_karti": "T.C. Kimlik Kartı Seri No/Geçerlilik Tarihi",
    "surucu_belgesi": "Sürücü Belgesi No",
    "yeni_surucu_belgesi": "Yeni Tip Sürücü Belgesi No/Geçerlilik Tarihi",
    "pasaport": "Pasaport No/Geçerlilik Tarihi",
    "ikamet_izni": "İkamet İzin Belgesi No/Geçerlilik Tarihi",
    "diger": "Diğer",
}

# (E) Şüpheli işlem.
ISLEM_DURUMU: Final = {"tesebbus": "Teşebbüs", "gerceklesmis": "Gerçekleşmiş"}
ISLEM_CESIDI: Final = {"tek": "Tek İşlem", "coklu": "Çoklu İşlem"}

# (F) Şüphe kategorileri — SK-Kodlari.pdf (41 kod).
SK_KODLARI: Final = {
    "SK-01": "Tefecilik",
    "SK-02": "POS tefeciliği",
    "SK-03": "Fuhuşa teşvik veya aracılık etmek",
    "SK-04": "Göçmen kaçakçılığı / insan ticareti",
    "SK-05": "Uyuşturucu madde ticareti",
    "SK-06": "Silah ve mühimmat kaçakçılığı",
    "SK-07": "Tarihi eser kaçakçılığı (kültür varlığı ticareti)",
    "SK-08": "Gümrük kaçakçılığı / hayali ihracat",
    "SK-09": "Kıymetli maden ve taşların kaçakçılığı",
    "SK-10": "Bilişim suçları",
    "SK-11": "Vergi kaçakçılığı ve vergi kaçırma",
    "SK-12": "Sermaye piyasalarına ilişkin suçlar",
    "SK-13": "Yolsuzluk ve kamu görevlileriyle ilgili suçlar (rüşvet, irtikap, zimmet, kamu "
    "görevlisinin haksız mal edinmesi ve diğer yolsuzluk ve görev suçları)",
    "SK-14": "Resmî / özel evrakta sahtecilik",
    "SK-15": "Para ve kıymetli evrak dolandırıcılığı / sahteciliği",
    "SK-16": "Sigorta dolandırıcılığı / poliçe sahteciliği",
    "SK-17": "Dolandırıcılık",
    "SK-18": "Organ ve doku ticareti",
    "SK-19": "Tehdit / şantaj / cebir ve adam kaçırma",
    "SK-20": "Mal varlığına karşı suçlar (hırsızlık, yağma vs.)",
    "SK-21": "Hileli iflas",
    "SK-22": "Yasa dışı bahis ve kumar oynatma/oynanmasına aracılık etme",
    "SK-23": "Terörizmin finansmanı",
    "SK-24": "İhaleye fesat karıştırma",
    "SK-25": "Sosyal güvenlik mevzuatına aykırılıklar",
    "SK-26": "Bankacılık mevzuatına ilişkin suçlar",
    "SK-27": "Akaryakıt kaçakçılığı",
    "SK-28": "Yasa dışı fatura ödeme merkezi faaliyetleri",
    "SK-29": "Lisanssız ödeme ve elektronik para hizmetlerinde bulunma",
    "SK-30": "Başkası hesabına işlem yapıldığının beyan edilmemesi",
    "SK-31": "Sigara, alkol ve tütün mamülleri kaçakçılığı",
    "SK-32": "Piramit satış sistemleri (saadet zincirleri)",
    "SK-33": "Sivil toplum kuruluşlarının suiistimali",
    "SK-34": "Yasadışı yardım ve bağış toplama",
    "SK-35": "Mal varlığının dondurulması kararının ihlali",
    "SK-36": "Kitle imha silahlarının yayılmasının finansmanı",
    "SK-37": "Yükümlülüklere Aykırı Hareket Edilmesi",
    "SK-38": "Müstehcenlik",
    "SK-39": "İzinsiz KVHS Faaliyeti",
    "SK-40": "Yabancı Kamu Görevlilerine Rüşvet Verilmesi",
    "SK-41": "Fiyatları Etkileme",
}
# §4.2.6: terörizmin finansmanında SK-23 ya da SK-35; KİS finansmanında SK-36 "kullanılacaktır".
KATEGORI_ZORUNLU_SK: Final = {
    "teror": frozenset({"SK-23", "SK-35"}),
    "kis": frozenset({"SK-36"}),
}
