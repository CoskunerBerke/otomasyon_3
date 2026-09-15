"""
The Indian places added to BuildVerse's story pool on 2026-09-16.

BuildVerse's Instagram audience is 60-70% Indian and not one place in the pool was. These
tests hold the two things that make an addition like this safe to publish, not merely
present:

  * every title it can produce is true. Hampi is a living village, Fatehpur Sikri a town,
    and fishing families still live at Dhanushkodi, so "Why Nobody Lives in X Anymore" is
    false for them -- and it is exactly what the plain "abandonment" frame hands out.
  * every sound description stays diegetic. The mode bans narration and a music
    soundtrack; an instrument written into ambience is what Flow renders as a score.
"""
import re

import pytest

from automation.content.story_concepts import STORY_CONCEPTS, get_story_concept
from automation.publishing.metadata_builder import PublishingMetadataBuilder

INDIA = ["kuldhara", "hampi", "fatehpur-sikri", "dhanushkodi", "ajanta-caves", "dholavira"]
LIVED_IN_TODAY = ["hampi", "fatehpur-sikri", "dhanushkodi", "ajanta-caves"]


def _titles(slug, variations=12):
    concept = get_story_concept(slug)
    out = []
    for i in range(variations):
        title, desc, tags = PublishingMetadataBuilder.build_story_youtube_metadata(
            reel_id=f"REEL-2026-{7000 + i:04d}",
            name=concept.name,
            category_group=concept.category_group,
            real_basis=concept.real_basis,
            topic_description=concept.topic_description,
            narrative_frame=concept.narrative_frame,
        )
        out.append((title, desc, tags))
    return out


def test_all_six_places_are_in_the_pool():
    slugs = {c.id_slug for c in STORY_CONCEPTS}
    for slug in INDIA:
        assert slug in slugs, slug


@pytest.mark.parametrize("slug", INDIA)
def test_each_place_names_india_in_its_factual_basis(slug):
    """The documented basis is what the description quotes; the country must be in it."""
    assert "India" in get_story_concept(slug).real_basis


@pytest.mark.parametrize("slug", LIVED_IN_TODAY)
def test_places_still_lived_in_never_claim_nobody_lives_there(slug):
    for title, _desc, _tags in _titles(slug):
        assert "Nobody Lives" not in title, f"{slug}: {title}"
        assert "The Day" not in title, f"{slug}: {title}"


def test_kuldhara_may_say_nobody_lives_there_because_nobody_does():
    """A protected site with no residents: the plain abandonment frame is true for it."""
    assert get_story_concept("kuldhara").narrative_frame == "abandonment"


@pytest.mark.parametrize("slug", INDIA)
def test_each_place_gets_its_own_hashtag(slug):
    concept = get_story_concept(slug)
    expected = "#" + "".join(w.capitalize() if w.islower() else w for w in concept.name.split())
    for _title, _desc, tags in _titles(slug, variations=1):
        assert expected in tags, (slug, tags)


@pytest.mark.parametrize("slug", INDIA)
def test_each_place_uses_an_existing_theme_group(slug):
    """A new group would have no hashtag set and would unbalance the weekly round-robin."""
    assert get_story_concept(slug).category_group in PublishingMetadataBuilder.STORY_HASHTAG_MAP


FORBIDDEN_IN_SOUND = [
    "music", "song", "sing", "melody", "drum", "flute", "reed", "shehnai", "sitar",
    "voice", "speech", "speak", "talk", "chant", "narrat", "dialogue",
]


@pytest.mark.parametrize("slug", INDIA)
def test_sound_stays_diegetic(slug):
    for beat, description in get_story_concept(slug).ambient_sounds.items():
        lowered = description.lower()
        for word in FORBIDDEN_IN_SOUND:
            # Word-start match: a plain substring test flags "rising" and "closing" for
            # "sing", which is noise that would teach people to ignore this test.
            assert not re.search(r"\b" + word, lowered), f"{slug}/{beat}: '{word}' in {description!r}"


@pytest.mark.parametrize("slug", INDIA)
def test_description_carries_no_hashtags(slug):
    """Hashtags are joined on by the platform writer alone; a second copy here duplicates them."""
    for _title, desc, _tags in _titles(slug, variations=3):
        assert "#" not in desc, f"{slug}: {desc}"
