"""Tests for local_shape_cache — the fresh-always-wins, per-machine memory."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from migration_tool.analyzer import local_shape_cache as c


# ── apply_as_fallback: the core safety property ───────────────────────────────

def test_fresh_method_is_never_overridden_by_cache():
    """The exact trap this module exists to prevent: a shape can genuinely
    change between apps, so a stale cached value must never win over fresh
    evidence from the current app."""
    cache = {'com.bbt.cmn.Foo': {'methods': {'getBar#0': {'return_type': 'String', 'static': False}}}}
    fresh = {'com.bbt.cmn.Foo': {'methods': {'getBar#0': {'return_type': 'FooResult', 'static': False}}}}
    applied = c.apply_as_fallback(fresh, cache)
    assert applied['com.bbt.cmn.Foo']['methods']['getBar#0']['return_type'] == 'FooResult'
    assert 'from_cache' not in applied['com.bbt.cmn.Foo']['methods']['getBar#0']


def test_cache_fills_a_method_not_seen_this_run():
    cache = {'com.bbt.cmn.Foo': {'methods': {'legacyOnly#0': {'return_type': None, 'static': False}}}}
    fresh = {'com.bbt.cmn.Foo': {'methods': {'getBar#0': {'return_type': 'String', 'static': False}}}}
    applied = c.apply_as_fallback(fresh, cache)
    assert applied['com.bbt.cmn.Foo']['methods']['legacyOnly#0']['from_cache'] is True
    assert applied['com.bbt.cmn.Foo']['methods']['getBar#0'].get('from_cache') is None


def test_type_absent_from_fresh_is_never_resurrected_from_cache_alone():
    """If this app's own code doesn't reference a type at all, no stub should
    be generated for it — regardless of what a previous app's cache knows."""
    cache = {'com.bbt.cmn.Foo': {'methods': {'getBar#0': {'return_type': 'String', 'static': False}}}}
    assert c.apply_as_fallback({}, cache) == {}


def test_apply_as_fallback_does_not_mutate_inputs():
    cache = {'com.bbt.cmn.Foo': {'methods': {'legacyOnly#0': {'return_type': None, 'static': False}}}}
    fresh = {'com.bbt.cmn.Foo': {'methods': {'getBar#0': {'return_type': 'String', 'static': False}}}}
    cache_before = {k: dict(v) for k, v in cache.items()}
    fresh_before = {k: dict(v) for k, v in fresh.items()}
    c.apply_as_fallback(fresh, cache)
    assert cache == cache_before
    assert fresh == fresh_before


# ── merge_fresh_into_cache: what actually gets persisted ─────────────────────

def test_merge_lets_fresh_correct_a_stale_cache_entry():
    cache = {'com.bbt.cmn.Foo': {'methods': {'getBar#0': {'return_type': 'String', 'static': False}}}}
    fresh = {'com.bbt.cmn.Foo': {'methods': {'getBar#0': {'return_type': 'FooResult', 'static': False}}}}
    updated = c.merge_fresh_into_cache(cache, fresh)
    assert updated['com.bbt.cmn.Foo']['methods']['getBar#0']['return_type'] == 'FooResult'


def test_merge_preserves_untouched_cache_entries():
    cache = {'com.bbt.cmn.Other': {'methods': {'m#0': {'return_type': None, 'static': False}}}}
    updated = c.merge_fresh_into_cache(cache, {})
    assert updated == cache


def test_merge_adds_brand_new_types():
    updated = c.merge_fresh_into_cache({}, {'com.bbt.cmn.New': {'methods': {'m#0': {'return_type': None, 'static': False}}}})
    assert 'com.bbt.cmn.New' in updated


def test_merge_never_persists_a_from_cache_marker():
    """A gap-filled entry re-observed fresh must be saved as clean fresh data,
    not carry the from_cache flag forward into the persisted cache."""
    cache = {'com.bbt.cmn.Foo': {'methods': {'m#0': {'return_type': None, 'static': False}}}}
    fresh = {'com.bbt.cmn.Foo': {'methods': {'m#0': {'return_type': 'X', 'static': False, 'from_cache': True}}}}
    updated = c.merge_fresh_into_cache(cache, fresh)
    assert 'from_cache' not in updated['com.bbt.cmn.Foo']['methods']['m#0']


# ── load/save round-trip and graceful degradation ────────────────────────────

def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / 'cache.json'
    data = {'com.bbt.cmn.Foo': {'methods': {'m#0': {'return_type': 'String', 'static': False}}}}
    c.save(data, path=path)
    assert c.load(path=path) == data


def test_load_returns_empty_dict_when_file_missing(tmp_path):
    assert c.load(path=tmp_path / 'does-not-exist.json') == {}


def test_load_returns_empty_dict_on_corrupt_json(tmp_path):
    path = tmp_path / 'corrupt.json'
    path.write_text('{not valid json', encoding='utf-8')
    assert c.load(path=path) == {}


def test_save_never_raises_on_unwritable_path(tmp_path):
    # a path whose parent is actually a file, not a directory — mkdir must fail
    blocker = tmp_path / 'blocker'
    blocker.write_text('x', encoding='utf-8')
    bad_path = blocker / 'sub' / 'cache.json'
    c.save({'x': {'methods': {}}}, path=bad_path)  # must not raise
