"""
YouTube localized titles and descriptions for BuildVerse's story and cutaway Reels.

Why: BuildVerse's videos carry no speech and no on-screen text, so the picture is already
understood everywhere. What was not is everything around it -- the title and description
were English only, while the channel's viewers are spread across Turkey, the US, India,
Indonesia and Japan. YouTube shows a viewer the localization that matches their interface
language, on the same video, with no second upload.

Deterministic by design, like the rest of the metadata: no model is called at publish
time. The translations live here as data, reviewable in a diff.

The contract that matters most: a localized title must be the same sentence as the English
one. Every template list below has the same length and order as its English counterpart in
PublishingMetadataBuilder.STORY_TITLE_VARIATIONS, and the index is taken from the same hash,
so a Reel titled "Why Nobody Lives in X Anymore" in English can never be titled "X, Then
and Now" in Hindi -- and, more importantly, a "left_behind" place can never pick up the
"nobody lives here" claim in another language that its English title was kept free of.
tests/test_youtube_localizations.py enforces the parity.
"""
from typing import Dict

LANGUAGES = ("tr", "hi", "id", "ja")

# ---------------------------------------------------------------------------------------
# Title templates, frame by frame, in the same order as the English pool.
#
# Turkish avoids any suffix on {title}: the right case ending depends on the vowels of the
# name ("Pompeii'ye", "Petra'ya"), which a template cannot know, so every Turkish pattern
# puts the name first and hangs the sentence off a colon.
# ---------------------------------------------------------------------------------------
TITLE_TEMPLATES: Dict[str, Dict[str, list]] = {
    "tr": {
        "abandonment": [
            "{title}: Geride Bırakılan Yer",
            "{title}: Burada Ne Oldu?",
            "{title}: Neden Artık Kimse Yaşamıyor?",
            "{title}: Dün ve Bugün",
            "{title}: Terk Edildiği Gün",
        ],
        "left_behind": [
            "{title}: Geride Bırakılan Yer",
            "{title}: Burada Ne Oldu?",
            "{title}: Dün ve Bugün",
            "30 Saniyede {title}",
        ],
        "cutaway": [
            "{title}: İçinde Aslında Ne Var?",
            "{title}: Altında Kimsenin Görmediği Dünya",
            "{title}: Yüzeyin Sakladığı",
            "Kesit: {title}",
            "{title}: Üstünden Geçtin Ama Hiç Bilmedin",
        ],
        "burial": [
            "{title}: Gömüldü, Sonra Yeniden Bulundu",
            "{title}: Toprağın Altında Ne Vardı?",
            "{title}: Gömülmeden Önce ve Sonra",
            "30 Saniyede {title}",
            "{title}: Nasıl Ortadan Kayboldu?",
        ],
        "vanishing": [
            "{title}: Su Nereye Gitti?",
            "{title}: Geriye Ne Kaldı?",
            "{title}: Dün ve Bugün",
            "30 Saniyede {title}",
        ],
        "creation": [
            "{title}: Nasıl Yapıldı?",
            "{title}: Nasıl Ortaya Çıktı?",
            "30 Saniyede {title}",
        ],
    },
    "hi": {
        "abandonment": [
            "{title}: वह जगह जिसे पीछे छोड़ दिया गया",
            "{title} का क्या हुआ?",
            "{title} में अब कोई क्यों नहीं रहता?",
            "{title}: तब और अब",
            "जिस दिन {title} को छोड़ दिया गया",
        ],
        "left_behind": [
            "{title}: वह जगह जिसे पीछे छोड़ दिया गया",
            "{title} का क्या हुआ?",
            "{title}: तब और अब",
            "30 सेकंड में {title} की कहानी",
        ],
        "cutaway": [
            "{title} के अंदर असल में क्या है?",
            "{title} के नीचे की दुनिया, जिसे कोई नहीं देखता",
            "{title}: सतह के नीचे क्या छिपा है",
            "अंदर से देखिए: {title}",
            "आप {title} के ऊपर से गुज़रे, पर कभी जाना नहीं",
        ],
        "burial": [
            "{title}: दफ़न हुआ, फिर दोबारा मिला",
            "{title} में क्या दफ़न था?",
            "{title}: दफ़न होने से पहले और बाद",
            "30 सेकंड में {title} की कहानी",
            "{title} कैसे गायब हो गया?",
        ],
        "vanishing": [
            "{title}: पानी कहाँ चला गया?",
            "{title} में अब क्या बचा है?",
            "{title}: तब और अब",
            "30 सेकंड में {title} की कहानी",
        ],
        "creation": [
            "{title} कैसे बना",
            "{title} कैसे अस्तित्व में आया",
            "30 सेकंड में {title} की कहानी",
        ],
    },
    "id": {
        "abandonment": [
            "{title}: Tempat yang Ditinggalkan",
            "Apa yang Terjadi pada {title}?",
            "Mengapa Tak Ada Lagi yang Tinggal di {title}?",
            "{title}, Dulu dan Sekarang",
            "Hari Ketika {title} Ditinggalkan",
        ],
        "left_behind": [
            "{title}: Tempat yang Ditinggalkan",
            "Apa yang Terjadi pada {title}?",
            "{title}, Dulu dan Sekarang",
            "Kisah {title} dalam 30 Detik",
        ],
        "cutaway": [
            "Apa Sebenarnya yang Ada di Dalam {title}?",
            "Dunia di Bawah {title} yang Tak Pernah Terlihat",
            "{title}: Yang Disembunyikan Permukaan",
            "Dibelah: {title}",
            "Kamu Pernah Melewati {title} Tanpa Pernah Tahu",
        ],
        "burial": [
            "{title}: Terkubur, Lalu Ditemukan Kembali",
            "Apa yang Terkubur di {title}?",
            "{title}, Sebelum dan Sesudah Terkubur",
            "Kisah {title} dalam 30 Detik",
            "Bagaimana {title} Menghilang",
        ],
        "vanishing": [
            "{title}: Ke Mana Airnya Pergi?",
            "Apa yang Tersisa dari {title}?",
            "{title}, Dulu dan Sekarang",
            "Kisah {title} dalam 30 Detik",
        ],
        "creation": [
            "Kisah Terbentuknya {title}",
            "Bagaimana {title} Terbentuk",
            "Kisah {title} dalam 30 Detik",
        ],
    },
    "ja": {
        "abandonment": [
            "{title}：置き去りにされた場所",
            "{title}に何が起きたのか",
            "なぜ{title}には誰も住まなくなったのか",
            "{title}の今と昔",
            "{title}が見捨てられた日",
        ],
        "left_behind": [
            "{title}：置き去りにされた場所",
            "{title}に何が起きたのか",
            "{title}の今と昔",
            "30秒でわかる{title}の物語",
        ],
        "cutaway": [
            "{title}の内部は実際どうなっているのか",
            "誰も見たことがない{title}の下の世界",
            "{title}：地表が隠しているもの",
            "断面図：{title}",
            "いつも歩いている{title}の下に、こんな世界が",
        ],
        "burial": [
            "{title}：埋もれ、そして再発見された",
            "{title}に埋もれていたもの",
            "{title}：埋もれる前と後",
            "30秒でわかる{title}の物語",
            "{title}はどうやって消えたのか",
        ],
        "vanishing": [
            "{title}：水はどこへ消えたのか",
            "{title}に残されたもの",
            "{title}の今と昔",
            "30秒でわかる{title}の物語",
        ],
        "creation": [
            "{title}ができるまで",
            "{title}はどのように生まれたのか",
            "30秒でわかる{title}の物語",
        ],
    },
}

# ---------------------------------------------------------------------------------------
# Cutaway subjects are common nouns, not places, so they always translate.
# ---------------------------------------------------------------------------------------
CUTAWAY_NAMES: Dict[str, Dict[str, str]] = {
    "tr": {
        "Canal Locks": "Kanal Havuzları",
        "Church Floors": "Kilise Zeminleri",
        "Football Pitches": "Futbol Sahaları",
        "Motorway Embankments": "Otoyol Setleri",
        "City Streets": "Şehir Sokakları",
        "Dam Walls": "Baraj Duvarları",
        "Quiet Fields": "Sessiz Tarlalar",
        "Salt Hills": "Tuz Tepeleri",
        "Old Tiled Floors": "Eski Karo Zeminler",
        "Lighthouses": "Deniz Fenerleri",
        "Grain Silos": "Tahıl Siloları",
        "Arena Floors": "Arena Zeminleri",
        "River Embankments": "Nehir Setleri",
        "Glaciers": "Buzullar",
        "Bridge Piers": "Köprü Ayakları",
        "Rock Overhangs": "Kaya Çıkıntıları",
    },
    "hi": {
        "Canal Locks": "नहर के लॉक",
        "Church Floors": "चर्च के फ़र्श",
        "Football Pitches": "फ़ुटबॉल के मैदान",
        "Motorway Embankments": "हाईवे के तटबंध",
        "City Streets": "शहर की सड़कें",
        "Dam Walls": "बांध की दीवारें",
        "Quiet Fields": "शांत खेत",
        "Salt Hills": "नमक की पहाड़ियाँ",
        "Old Tiled Floors": "पुराने टाइल वाले फ़र्श",
        "Lighthouses": "लाइटहाउस",
        "Grain Silos": "अनाज के साइलो",
        "Arena Floors": "अखाड़ों के फ़र्श",
        "River Embankments": "नदी के तटबंध",
        "Glaciers": "ग्लेशियर",
        "Bridge Piers": "पुल के खंभे",
        "Rock Overhangs": "चट्टानों के छज्जे",
    },
    "id": {
        "Canal Locks": "Pintu Air Kanal",
        "Church Floors": "Lantai Gereja",
        "Football Pitches": "Lapangan Sepak Bola",
        "Motorway Embankments": "Tanggul Jalan Tol",
        "City Streets": "Jalanan Kota",
        "Dam Walls": "Dinding Bendungan",
        "Quiet Fields": "Ladang yang Sunyi",
        "Salt Hills": "Bukit Garam",
        "Old Tiled Floors": "Lantai Ubin Tua",
        "Lighthouses": "Mercusuar",
        "Grain Silos": "Silo Gandum",
        "Arena Floors": "Lantai Arena",
        "River Embankments": "Tanggul Sungai",
        "Glaciers": "Gletser",
        "Bridge Piers": "Pilar Jembatan",
        "Rock Overhangs": "Tebing Batu Menjorok",
    },
    "ja": {
        "Canal Locks": "運河の閘門",
        "Church Floors": "教会の床",
        "Football Pitches": "サッカー場",
        "Motorway Embankments": "高速道路の盛土",
        "City Streets": "街の通り",
        "Dam Walls": "ダムの壁",
        "Quiet Fields": "静かな畑",
        "Salt Hills": "塩の丘",
        "Old Tiled Floors": "古いタイルの床",
        "Lighthouses": "灯台",
        "Grain Silos": "穀物サイロ",
        "Arena Floors": "闘技場の床",
        "River Embankments": "川の堤防",
        "Glaciers": "氷河",
        "Bridge Piers": "橋脚",
        "Rock Overhangs": "岩のひさし",
    },
}

# ---------------------------------------------------------------------------------------
# Place names. Anything missing stays in its Latin form, which is how most of these places
# are searched for worldwide. An entry exists only where the local form is genuinely what
# that audience knows: the Indian places in Hindi, Hashima as 軍艦島, and names whose English
# carries a translatable word ("The Aral Sea", "Ross Island").
# ---------------------------------------------------------------------------------------
PLACE_NAMES: Dict[str, Dict[str, str]] = {
    "tr": {
        "The Aral Sea": "Aral Gölü",
        "The Salton Sea": "Salton Gölü",
        "Hashima Island": "Hashima Adası",
        "Ross Island": "Ross Adası",
        "Ajanta Caves": "Ajanta Mağaraları",
        "Rapa Nui": "Paskalya Adası",
    },
    "hi": {
        "Kuldhara": "कुलधरा",
        "Hampi": "हम्पी",
        "Fatehpur Sikri": "फ़तेहपुर सीकरी",
        "Dhanushkodi": "धनुषकोडी",
        "Ajanta Caves": "अजंता की गुफाएँ",
        "Dholavira": "धोलावीरा",
        "Pompeii": "पोम्पेई",
        "Petra": "पेट्रा",
        "Machu Picchu": "माचू पिच्चू",
        "Angkor": "अंकोर",
        "The Aral Sea": "अरल सागर",
        "The Salton Sea": "साल्टन सागर",
        "Hashima Island": "हाशिमा द्वीप",
        "Ross Island": "रॉस द्वीप",
    },
    "id": {
        "The Aral Sea": "Laut Aral",
        "The Salton Sea": "Laut Salton",
        "Hashima Island": "Pulau Hashima",
        "Ross Island": "Pulau Ross",
        "Ajanta Caves": "Gua Ajanta",
        "Rapa Nui": "Pulau Paskah",
    },
    "ja": {
        "Pompeii": "ポンペイ",
        "Herculaneum": "ヘルクラネウム",
        "Angkor": "アンコール",
        "Petra": "ペトラ",
        "Machu Picchu": "マチュピチュ",
        "Hashima Island": "軍艦島",
        "Pripyat": "プリピャチ",
        "The Aral Sea": "アラル海",
        "Derinkuyu": "デリンクユ",
        "Rapa Nui": "イースター島",
        "Tikal": "ティカル",
        "Ajanta Caves": "アジャンター石窟群",
        "Hampi": "ハンピ",
        "Fatehpur Sikri": "ファテープル・シークリー",
        "Ross Island": "ロス島",
        "The Salton Sea": "ソルトン湖",
    },
}

# ---------------------------------------------------------------------------------------
# A short opening line per language. The English description follows it, so no language
# is ever left with an empty description, and the AI disclosure reads in every one.
# ---------------------------------------------------------------------------------------
DESCRIPTION_INTROS: Dict[str, Dict[str, str]] = {
    "tr": {
        "story": "Gerçek bir yerin hikâyesi, 30 saniyede. Görüntüler yapay zekâ ile oluşturuldu, sesler doğal ortam sesidir.",
        "cutaway": "Bir yapının içi, kesit hâlinde, 30 saniyede. Görüntüler yapay zekâ ile oluşturuldu.",
    },
    "hi": {
        "story": "एक असली जगह की कहानी, 30 सेकंड में। दृश्य AI से बनाए गए हैं, आवाज़ें प्राकृतिक माहौल की हैं।",
        "cutaway": "किसी संरचना के अंदर का नज़ारा, 30 सेकंड में। दृश्य AI से बनाए गए हैं।",
    },
    "id": {
        "story": "Kisah sebuah tempat nyata dalam 30 detik. Visual dibuat dengan AI, suaranya adalah suara alam di lokasi.",
        "cutaway": "Bagian dalam sebuah struktur, dibelah dalam 30 detik. Visual dibuat dengan AI.",
    },
    "ja": {
        "story": "実在する場所の物語を30秒で。映像はAIで生成、音は現地の自然な環境音です。",
        "cutaway": "構造物の内部を断面で、30秒で。映像はAIで生成されています。",
    },
}

YOUTUBE_TITLE_LIMIT = 100


def localized_name(lang: str, name: str, narrative_frame: str) -> str:
    """The subject as that language shows it: cutaway nouns translate, places may not."""
    clean = (name or "").strip()
    if narrative_frame == "cutaway":
        return CUTAWAY_NAMES.get(lang, {}).get(clean, clean)
    return PLACE_NAMES.get(lang, {}).get(clean, clean)


def build_story_localizations(
    reel_id: str,
    name: str,
    narrative_frame: str,
    english_description: str,
) -> Dict[str, Dict[str, str]]:
    """
    {lang: {"title": ..., "description": ...}} for a story or cutaway Reel.

    The template index comes from the same hash PublishingMetadataBuilder uses for the
    English title, so every language says the same thing. Descriptions carry no hashtags:
    as with the English description, the publisher that writes to the platform is the one
    place they are joined on.

    Returns {} for an unknown frame rather than guessing one, so a Reel whose frame has no
    translations is published in English only instead of under the wrong claim.
    """
    from automation.publishing.metadata_builder import PublishingMetadataBuilder

    clean_name = (name or "").strip()
    english_pool = PublishingMetadataBuilder.STORY_TITLE_VARIATIONS.get(narrative_frame)
    if not clean_name or not english_pool:
        return {}

    index = PublishingMetadataBuilder._deterministic_hash(reel_id + clean_name) % len(english_pool)
    intro_kind = "cutaway" if narrative_frame == "cutaway" else "story"
    body = (english_description or "").strip()

    out: Dict[str, Dict[str, str]] = {}
    for lang in LANGUAGES:
        templates = TITLE_TEMPLATES.get(lang, {}).get(narrative_frame)
        if not templates or len(templates) != len(english_pool):
            continue
        title = templates[index].format(title=localized_name(lang, clean_name, narrative_frame))
        intro = DESCRIPTION_INTROS[lang][intro_kind]
        out[lang] = {
            "title": title[:YOUTUBE_TITLE_LIMIT],
            "description": f"{intro}\n\n{body}" if body else intro,
        }
    return out
