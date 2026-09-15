"""
Localized YouTube titles and descriptions (tr, hi, id, ja) for BuildVerse.

The videos carry no speech and no on-screen text, so the picture needs no translation --
the title and description around it did, and they were English only while the channel's
viewers sit in Turkey, the US, India, Indonesia and Japan.

The failure these tests exist to prevent is a translation that says something different
from the English title. Titles are picked from a pool by hash; if a language's pool were
shorter, longer or reordered, the same Reel would get a different sentence in that language
-- and a place kept free of "nobody lives here" in English could carry exactly that claim
in Hindi. Parity is therefore checked against the English pool, not against a copy of it.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from automation.content.cutaway_concepts import CUTAWAY_CONCEPTS
from automation.content.story_concepts import STORY_CONCEPTS
from automation.publishing import localizations as L
from automation.publishing.metadata_builder import PublishingMetadataBuilder as B

ENGLISH = B.STORY_TITLE_VARIATIONS
ALL_CONCEPTS = list(STORY_CONCEPTS) + list(CUTAWAY_CONCEPTS)


# --------------------------------------------------------------------------- parity

@pytest.mark.parametrize("lang", L.LANGUAGES)
def test_every_language_covers_every_english_frame(lang):
    assert set(L.TITLE_TEMPLATES[lang]) == set(ENGLISH), lang


@pytest.mark.parametrize("lang", L.LANGUAGES)
@pytest.mark.parametrize("frame", sorted(ENGLISH))
def test_template_pools_match_english_length(lang, frame):
    """Same length, so the same hash index lands on the same sentence."""
    assert len(L.TITLE_TEMPLATES[lang][frame]) == len(ENGLISH[frame]), (lang, frame)


@pytest.mark.parametrize("lang", L.LANGUAGES)
def test_every_template_places_the_name_exactly_once(lang):
    for frame, pool in L.TITLE_TEMPLATES[lang].items():
        for template in pool:
            assert template.count("{title}") == 1, (lang, frame, template)


# The one claim per language that must never reach a place that is still lived in.
NOBODY_LIVES = {
    "tr": "Kimse Yaşamıyor",
    "hi": "कोई क्यों नहीं रहता",
    "id": "Tak Ada Lagi yang Tinggal",
    "ja": "誰も住まなくなった",
}


@pytest.mark.parametrize("lang", L.LANGUAGES)
def test_nobody_lives_claim_sits_in_the_same_slot_as_english(lang):
    """Positional parity for the one sentence that can be false."""
    en_index = next(i for i, t in enumerate(ENGLISH["abandonment"]) if "Nobody Lives" in t)
    assert NOBODY_LIVES[lang] in L.TITLE_TEMPLATES[lang]["abandonment"][en_index]
    for frame, pool in L.TITLE_TEMPLATES[lang].items():
        if frame == "abandonment":
            continue
        for template in pool:
            assert NOBODY_LIVES[lang] not in template, (lang, frame, template)


@pytest.mark.parametrize("slug", ["hampi", "fatehpur-sikri", "dhanushkodi", "ajanta-caves"])
def test_lived_in_places_never_get_the_claim_in_any_language(slug):
    concept = next(c for c in STORY_CONCEPTS if c.id_slug == slug)
    for i in range(20):
        out = L.build_story_localizations(f"REEL-2026-{8000 + i:04d}", concept.name, concept.narrative_frame, "x")
        for lang, entry in out.items():
            assert NOBODY_LIVES[lang] not in entry["title"], (slug, lang, entry["title"])


# ----------------------------------------------------------------------- every concept

@pytest.mark.parametrize("concept", ALL_CONCEPTS, ids=lambda c: c.id_slug)
def test_every_concept_localizes_into_all_languages(concept):
    out = L.build_story_localizations("REEL-2026-0100", concept.name, concept.narrative_frame, "Base text.")
    assert set(out) == set(L.LANGUAGES), concept.id_slug
    for lang, entry in out.items():
        assert entry["title"].strip(), (concept.id_slug, lang)
        assert entry["description"].endswith("Base text."), "the English description must follow the intro"
        assert "#" not in entry["description"], "hashtags are added by the publisher alone"


@pytest.mark.parametrize("concept", ALL_CONCEPTS, ids=lambda c: c.id_slug)
def test_no_title_needs_truncating(concept):
    """Truncation would cut a sentence mid-word; every combination must fit on its own."""
    for lang in L.LANGUAGES:
        name = L.localized_name(lang, concept.name, concept.narrative_frame)
        for template in L.TITLE_TEMPLATES[lang][concept.narrative_frame]:
            assert len(template.format(title=name)) <= L.YOUTUBE_TITLE_LIMIT, (concept.id_slug, lang)


@pytest.mark.parametrize("lang", L.LANGUAGES)
def test_every_cutaway_subject_is_translated(lang):
    """Cutaway subjects are nouns: an untranslated one leaks English into the title."""
    for concept in CUTAWAY_CONCEPTS:
        assert concept.name in L.CUTAWAY_NAMES[lang], (lang, concept.name)


# English common words that must not survive inside another language's title.
ENGLISH_WORDS_IN_NAMES = ("Island", "Sea", "Caves")


@pytest.mark.parametrize("lang", L.LANGUAGES)
def test_no_english_common_word_leaks_from_a_place_name(lang):
    """
    "Hashima Island" once rendered in the middle of a Hindi sentence. A place name is left
    in Latin script on purpose, but a translatable word inside it is not a name.
    """
    for concept in STORY_CONCEPTS:
        if any(word in concept.name.split() for word in ENGLISH_WORDS_IN_NAMES):
            assert concept.name in L.PLACE_NAMES[lang], (lang, concept.name)


def test_unknown_frame_publishes_english_only_rather_than_guessing():
    assert L.build_story_localizations("REEL-2026-0100", "Somewhere", "no-such-frame", "x") == {}


def test_localized_title_follows_the_english_index():
    concept = next(c for c in STORY_CONCEPTS if c.id_slug == "pompeii")
    for i in range(10):
        reel_id = f"REEL-2026-{9000 + i:04d}"
        en_title, _d, _t = B.build_story_youtube_metadata(
            reel_id=reel_id, name=concept.name, category_group=concept.category_group,
            real_basis=concept.real_basis, topic_description=concept.topic_description,
            narrative_frame=concept.narrative_frame,
        )
        en_index = ENGLISH[concept.narrative_frame].index(
            next(t for t in ENGLISH[concept.narrative_frame] if t.format(title=concept.name) == en_title)
        )
        out = L.build_story_localizations(reel_id, concept.name, concept.narrative_frame, "x")
        name_tr = L.localized_name("tr", concept.name, concept.narrative_frame)
        assert out["tr"]["title"] == L.TITLE_TEMPLATES["tr"][concept.narrative_frame][en_index].format(title=name_tr)


# ------------------------------------------------------------------------- publisher

def _publisher_capturing_insert(tmp_path, monkeypatch, localizations_for):
    from automation.publishing import youtube_publisher as yp
    from automation.publishing.config import PublishingConfig
    from automation.publishing.models import Platform, PublishRecord

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 2048)

    captured = {}
    service = MagicMock()

    def insert(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after capture")

    service.videos.return_value.insert.side_effect = insert
    monkeypatch.setattr(yp.YouTubeAuthManager, "get_authenticated_service", staticmethod(lambda **k: service))
    monkeypatch.setattr(yp.YouTubeAuthManager, "verify_authenticated_channel",
                        staticmethod(lambda *a, **k: (True, "ok", {"title": "t", "custom_url": "@t"})))

    record = PublishRecord(
        publish_id="p", batch_id="b", reel_id="REEL-2026-0067", platform=Platform.YOUTUBE,
        video_file=video, video_sha256="0" * 64, title="Angkor, Then and Now", description="The Khmer capital.",
        hashtags=["#Shorts", "#Angkor"], scheduled_at_local="2026-09-14 19:30:00",
        scheduled_at_utc="2026-09-14T16:30:00Z",
    )
    publisher = yp.YouTubePublisher(PublishingConfig(), localizations_for=localizations_for)
    publisher.upload_and_schedule(record)
    return captured


def test_publisher_sends_localizations_with_hashtags_appended_once(tmp_path, monkeypatch):
    loc = {"hi": {"title": "अंकोर: तब और अब", "description": "परिचय\n\nThe Khmer capital."}}
    captured = _publisher_capturing_insert(tmp_path, monkeypatch, lambda record: loc)

    assert captured["part"] == "snippet,status,localizations"
    body = captured["body"]
    assert body["snippet"]["defaultLanguage"] == "en", "YouTube refuses localizations without it"
    assert body["localizations"]["hi"]["title"] == "अंकोर: तब और अब"
    hi_desc = body["localizations"]["hi"]["description"]
    assert hi_desc.count("#Angkor") == 1
    assert hi_desc.startswith("परिचय")


def test_a_failing_localizer_still_uploads_in_english(tmp_path, monkeypatch):
    def broken(record):
        raise ValueError("translation table missing")

    captured = _publisher_capturing_insert(tmp_path, monkeypatch, broken)
    assert captured["part"] == "snippet,status"
    assert "localizations" not in captured["body"]
    assert "defaultLanguage" not in captured["body"]["snippet"]


def test_publisher_without_a_localizer_is_unchanged(tmp_path, monkeypatch):
    captured = _publisher_capturing_insert(tmp_path, monkeypatch, None)
    assert captured["part"] == "snippet,status"


# -------------------------------------------------------------------------- pipeline

def _pipeline_with_reel(content_mode, slug):
    from automation.simple_weekly_pipeline import SimpleWeeklyPipeline

    pipe = SimpleWeeklyPipeline.__new__(SimpleWeeklyPipeline)
    pipe.week_id = "2026-W39"
    reel = MagicMock(reel_id="REEL-2026-0081", content_mode=content_mode, concept_id_slug=slug)
    pipe.batch_repo = MagicMock()
    pipe.batch_repo.load_manifest.return_value = MagicMock(reels=[reel])
    return pipe, MagicMock(reel_id="REEL-2026-0081", description="The Khmer capital.")


def test_pipeline_resolves_the_generated_concept():
    from automation.content.content_modes import NARRATIVE_AMBIENT_STORY

    pipe, record = _pipeline_with_reel(NARRATIVE_AMBIENT_STORY, "hampi")
    out = pipe._youtube_localizations(record)
    assert set(out) == set(L.LANGUAGES)
    assert "हम्पी" in out["hi"]["title"]


def test_pipeline_leaves_other_modes_in_english():
    from automation.content.content_modes import HIDDEN_BUILD_STORY

    pipe, record = _pipeline_with_reel(HIDDEN_BUILD_STORY, "yacht-cellar")
    assert pipe._youtube_localizations(record) == {}


def test_pipeline_unknown_concept_is_english_only_not_an_error():
    from automation.content.content_modes import NARRATIVE_AMBIENT_STORY

    pipe, record = _pipeline_with_reel(NARRATIVE_AMBIENT_STORY, "no-such-place")
    assert pipe._youtube_localizations(record) == {}
