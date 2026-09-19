"""
Regression: the channel republishing itself on a fortnightly cycle.

2026-09-20. BuildVerse's views fell, and the manifests say why before any analytics does:
2026-W38 published eleven of 2026-W36's fourteen concepts, six of them under a title that
was byte-identical to the earlier one. "Machu Picchu, Then and Now" went out on 26 August,
5 September and 17 September.

The cause was one line of policy in _fresh_plans -- "Only the previous week is excluded,
not all history". Skip exactly one week and the week before it is free to return, so the
pool oscillated between two sets forever. Ranking could not break the tie either: the
category penalty compares a content_mode string against concept slugs and never matches,
so every week came out in the same order.

Rotation is now the channel's own history: never-aired concepts first, then whoever has
waited longest, with a rest period sized to what the pool can actually honour.
"""
import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.content.cutaway_concepts import CUTAWAY_CONCEPTS
from automation.publishing.metadata_builder import PublishingMetadataBuilder
from automation.simple_weekly_pipeline import SimpleWeeklyPipeline

WEEK_START = datetime.date(2026, 9, 21)


def _plan(slug, group="Group A"):
    return SimpleNamespace(concept_def=SimpleNamespace(id_slug=slug, category_group=group))


def _engine(plans):
    """An engine whose ranking is fixed -- which is what the real one does in practice."""
    return SimpleNamespace(
        provider=SimpleNamespace(categories=plans),
        generate_next_reels=lambda count, past_records, duration_seconds: list(plans),
    )


def _pipeline():
    p = SimpleWeeklyPipeline.__new__(SimpleWeeklyPipeline)
    p.content_mode = "narrative_ambient_story"
    return p


# ------------------------------------------------------------------ rest period

@pytest.mark.parametrize("pool,per_week,expected", [
    (33, 7, 21),   # story: three weeks of depth, capped at the ceiling
    (16, 7, 7),    # cutaway: two weeks of depth is all it can honour
    (24, 7, 14),   # what deepening the cutaway pool would buy
    (7, 7, 0),     # a pool exactly one week deep cannot rest anything
    (33, 0, 0),
])
def test_the_rest_period_is_what_the_pool_can_afford(pool, per_week, expected):
    """
    A fixed 21 days would have left the 16-concept cutaway pool with nothing to publish
    in week three -- a rotation rule that turns into an outage is not a rotation rule.
    """
    assert SimpleWeeklyPipeline._quarantine_days(pool, per_week, 21) == expected


# ------------------------------------------------------------------ selection

def test_never_aired_concepts_go_first():
    """
    The six Indian places added on 2026-09-15 sat unused while the pool re-served
    September's videos: ranking put them nowhere near the top and nothing else looked at
    whether a concept had ever aired.
    """
    plans = [_plan("old-a"), _plan("old-b"), _plan("fresh-a"), _plan("fresh-b")]
    last_aired = {"old-a": WEEK_START - datetime.timedelta(days=30),
                  "old-b": WEEK_START - datetime.timedelta(days=40)}

    chosen = _pipeline()._fresh_plans(_engine(plans), 2, [], last_aired, WEEK_START)

    assert {c.concept_def.id_slug for c in chosen} == {"fresh-a", "fresh-b"}


def test_a_concept_from_two_weeks_ago_is_not_served_again():
    """The exact W36 -> W38 repeat: 14 days is not a rotation, it is a rerun."""
    plans = [_plan("machu-picchu"), _plan("derinkuyu"), _plan("pripyat"), _plan("craco")]
    last_aired = {"machu-picchu": WEEK_START - datetime.timedelta(days=14),
                  "derinkuyu": WEEK_START - datetime.timedelta(days=14)}

    chosen = _pipeline()._fresh_plans(_engine(plans), 2, [], last_aired, WEEK_START)
    slugs = {c.concept_def.id_slug for c in chosen}

    assert "machu-picchu" not in slugs and "derinkuyu" not in slugs


def test_the_longest_waiting_concept_comes_back_first():
    plans = [_plan("recent"), _plan("older"), _plan("oldest")]
    last_aired = {
        "recent": WEEK_START - datetime.timedelta(days=22),
        "older": WEEK_START - datetime.timedelta(days=40),
        "oldest": WEEK_START - datetime.timedelta(days=90),
    }

    chosen = _pipeline()._fresh_plans(_engine(plans), 2, [], last_aired, WEEK_START)

    assert [c.concept_def.id_slug for c in chosen] == ["oldest", "older"]


def test_a_shallow_pool_still_fills_the_week_and_says_so(caplog):
    """
    Refusing to publish is worse than publishing a shorter gap, but doing it silently is
    how a rotation quietly stops rotating. The 16-concept cutaway pool is in exactly this
    position until it is deepened.
    """
    # Eight concepts at four a week buys a 7-day rest; every one of them aired two days
    # ago, so the rest cannot be honoured for anybody.
    slugs = [f"c{i}" for i in range(8)]
    plans = [_plan(s, f"Group {i % 4}") for i, s in enumerate(slugs)]
    last_aired = {s: WEEK_START - datetime.timedelta(days=2) for s in slugs}

    with caplog.at_level("WARNING"):
        chosen = _pipeline()._fresh_plans(_engine(plans), 4, [], last_aired, WEEK_START)

    assert len(chosen) == 4
    assert "dinlenme tam saglanamadi" in caplog.text


def test_a_week_does_not_open_with_four_of_the_same_category():
    """
    Putting never-aired concepts first must not undo the group round-robin: five unused
    Indian places would otherwise land back to back.
    """
    plans = [_plan(f"india-{i}", "Buried by Nature") for i in range(4)] + \
            [_plan(f"other-{i}", f"Group {i}") for i in range(4)]

    chosen = _pipeline()._fresh_plans(_engine(plans), 4, [], {}, WEEK_START)
    groups = [c.concept_def.category_group for c in chosen]

    assert groups.count("Buried by Nature") <= 2, f"kategori yigilmasi: {groups}"


# ------------------------------------------------------------------ the guard

def test_a_repeat_inside_a_week_stops_the_run():
    plans = [_plan("bodie")]
    last_aired = {"bodie": WEEK_START - datetime.timedelta(days=3)}

    with pytest.raises(RuntimeError, match="CONCEPT_POOL_EXHAUSTED"):
        _pipeline()._refuse_a_repeat_within_days(plans, last_aired, WEEK_START)


def test_a_rested_concept_passes_the_guard():
    plans = [_plan("bodie")]
    last_aired = {"bodie": WEEK_START - datetime.timedelta(days=21)}

    _pipeline()._refuse_a_repeat_within_days(plans, last_aired, WEEK_START)  # raises nothing


def test_the_guard_no_longer_asks_only_about_last_week():
    """
    The old check compared against the previous week alone, so the repeat it existed to
    catch -- W38 republishing W36 -- walked straight past it.
    """
    source = (Path(__file__).resolve().parents[1]
              / "automation" / "simple_weekly_pipeline.py").read_text(encoding="utf-8")
    assert "_last_week_concept_slugs" not in source
    assert "Only the previous week is excluded" not in source


# ------------------------------------------------------------------ history

def test_history_reads_every_week_and_keeps_the_latest_airing(tmp_path):
    p = _pipeline()
    p.brand = SimpleNamespace(owns_week_id=lambda w: w.startswith("2026-W"))
    weeks = {
        "2026-W36": [("machu-picchu", "2026-09-05 19:30")],
        "2026-W38": [("machu-picchu", "2026-09-17 19:30"), ("bodie", "2026-09-16 19:30")],
        "CBM-2026-W38": [("submarine-gym", "2026-09-18 19:30")],  # other brand
    }

    def load(week_id):
        rows = weeks.get(week_id)
        if rows is None:
            return None
        return SimpleNamespace(reels=[
            SimpleNamespace(concept_id_slug=s, scheduled_at_local=d) for s, d in rows
        ])

    for w in weeks:
        (tmp_path / w).mkdir()
    p.batch_repo = SimpleNamespace(batches_dir=tmp_path, load_manifest=load)

    aired = p._concept_last_aired()

    assert aired["machu-picchu"] == datetime.date(2026, 9, 17), "en son yayin tarihi kazanmali"
    assert aired["bodie"] == datetime.date(2026, 9, 16)
    assert "submarine-gym" not in aired, "diger markanin haftasi sayilmamali"


# ------------------------------------------------------------------ hashtags

def test_every_cutaway_group_has_its_own_hashtags():
    """
    All 21 cutaway Reels published between 31 August and 20 September carried the same
    five tags -- #History #LostPlaces #Archaeology #Abandoned #Documentary -- because the
    map had no entry for any of their groups and they fell through to the abandonment
    fallback. A working dam gallery was being handed to an audience that came for ruins.
    """
    groups = {c.category_group for c in CUTAWAY_CONCEPTS}
    missing = groups - set(PublishingMetadataBuilder.STORY_HASHTAG_MAP)

    assert not missing, f"fallback'e dusen cutaway grubu: {missing}"


def test_a_cutaway_reel_is_not_tagged_as_an_abandoned_place():
    concept = next(c for c in CUTAWAY_CONCEPTS if c.category_group == "Engineering Interiors")

    _title, _desc, tags = PublishingMetadataBuilder.build_story_youtube_metadata(
        reel_id="REEL-2026-0100",
        name=concept.name,
        category_group=concept.category_group,
        real_basis=concept.real_basis,
        topic_description=concept.topic_description,
        narrative_frame=getattr(concept, "narrative_frame", "cutaway"),
    )

    assert "#Abandoned" not in tags and "#LostPlaces" not in tags
    assert "#Engineering" in tags
