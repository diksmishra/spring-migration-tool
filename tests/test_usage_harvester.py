"""Tests for usage_harvester — the --unavailable-packages usage-discovery step."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from migration_tool.analyzer import usage_harvester as h


FULL_NAME = 'com.bbt.cmn.util.services.CommonUtilityBeanLocal'


def _targets():
    return {'CommonUtilityBeanLocal': FULL_NAME}


# ── unavailable_import_targets ────────────────────────────────────────────────

def test_finds_matching_import():
    src = 'import com.bbt.cmn.util.services.CommonUtilityBeanLocal;\n'
    targets = h.unavailable_import_targets(src, ['com.bbt.cmn'])
    assert targets == {'CommonUtilityBeanLocal': FULL_NAME}


def test_ignores_non_matching_prefix():
    src = 'import com.other.Foo;\n'
    assert h.unavailable_import_targets(src, ['com.bbt.cmn']) == {}


def test_skips_wildcard_imports():
    src = 'import com.bbt.cmn.util.*;\n'
    assert h.unavailable_import_targets(src, ['com.bbt.cmn']) == {}


def test_no_prefixes_means_no_targets():
    src = 'import com.bbt.cmn.util.services.CommonUtilityBeanLocal;\n'
    assert h.unavailable_import_targets(src, []) == {}


# ── harvest: direct instance/static calls ─────────────────────────────────────

def test_harvests_direct_instance_call():
    src = (
        'import com.bbt.cmn.util.services.CommonUtilityBeanLocal;\n'
        'public class Foo {\n'
        '    private CommonUtilityBeanLocal svc;\n'
        '    void m() { svc.doThing(); }\n'
        '}\n'
    )
    result = h.harvest(src, _targets())
    assert 'doThing#0' in result[FULL_NAME]['methods']
    assert result[FULL_NAME]['methods']['doThing#0']['static'] is False


def test_harvests_static_call():
    src = (
        'import com.bbt.cmn.util.services.CommonUtilityBeanLocal;\n'
        'public class Foo {\n'
        '    void m() { CommonUtilityBeanLocal.staticHelper(); }\n'
        '}\n'
    )
    result = h.harvest(src, _targets())
    assert result[FULL_NAME]['methods']['staticHelper#0']['static'] is True


def test_overloads_with_different_arg_counts_kept_separate():
    src = (
        'import com.bbt.cmn.util.services.CommonUtilityBeanLocal;\n'
        'public class Foo {\n'
        '    private CommonUtilityBeanLocal svc;\n'
        '    void m() { svc.doThing(); svc.doThing(1, 2); }\n'
        '}\n'
    )
    methods = h.harvest(src, _targets())[FULL_NAME]['methods']
    assert 'doThing#0' in methods
    assert 'doThing#2' in methods


def test_return_type_inferred_from_declaration():
    src = (
        'import com.bbt.cmn.util.services.CommonUtilityBeanLocal;\n'
        'import java.util.Set;\n'
        'public class Foo {\n'
        '    private CommonUtilityBeanLocal svc;\n'
        '    void m() { Set<String> result = svc.getValues(); }\n'
        '}\n'
    )
    methods = h.harvest(src, _targets())[FULL_NAME]['methods']
    assert methods['getValues#0']['return_type'] == 'Set<String>'


def test_return_type_none_when_result_unused():
    src = (
        'import com.bbt.cmn.util.services.CommonUtilityBeanLocal;\n'
        'public class Foo {\n'
        '    private CommonUtilityBeanLocal svc;\n'
        '    void m() { svc.doThing(); }\n'
        '}\n'
    )
    methods = h.harvest(src, _targets())[FULL_NAME]['methods']
    assert methods['doThing#0']['return_type'] is None


# ── known v1 gaps, explicitly verified rather than assumed ────────────────────

def test_chained_call_continuation_not_captured():
    """foo.getInner() is captured (direct call); .doThing() on its result is not
    (javalang has no parent pointers to attribute a chain continuation)."""
    src = (
        'import com.bbt.cmn.Foo;\n'
        'public class Bar {\n'
        '    void m(Foo foo) { foo.getInner().doThing(); }\n'
        '}\n'
    )
    methods = h.harvest(src, {'Foo': 'com.bbt.cmn.Foo'})['com.bbt.cmn.Foo']['methods']
    assert 'getInner#0' in methods
    assert 'doThing#0' not in methods


def test_type_used_with_extends_is_excluded_entirely():
    src = (
        'import com.bbt.cmn.SomeBase;\n'
        'public class Foo extends SomeBase {\n'
        '    void m(SomeBase someBase) { someBase.doThing(); }\n'
        '}\n'
    )
    result = h.harvest(src, {'SomeBase': 'com.bbt.cmn.SomeBase'})
    assert result == {}


# ── graceful degradation ──────────────────────────────────────────────────────

def test_harvest_returns_empty_dict_on_unparseable_source():
    assert h.harvest('this is not valid java {{{', _targets()) == {}


def test_harvest_returns_empty_dict_when_no_type_names():
    assert h.harvest('public class Foo {}', {}) == {}
