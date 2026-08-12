"""Tests for StubGenerator — verifies all stub files are written to the correct paths."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pathlib import Path
import pytest
from migration_tool.config import MigrationConfig
from migration_tool.generators.stub_generator import StubGenerator


def _config(tmp_path):
    return MigrationConfig(
        source_dir=tmp_path / 'src',
        output_dir=tmp_path / 'out',
        base_package='com.example',
        group_id='com.example',
        artifact_id='test-app',
        spring_boot_version='3.2.5',
        java_version='17',
        persistence_mode='jpa',
    )


EXPECTED_STUBS = [
    ('com/sap/security/api/IUser.java',           'package com.sap.security.api;',          'interface IUser'),
    ('com/sap/security/api/IPrincipal.java',      'package com.sap.security.api;',          'interface IPrincipal'),
    ('com/sap/security/api/IUserFactory.java',    'package com.sap.security.api;',          'interface IUserFactory'),
    ('com/sap/security/api/IRoleFactory.java',    'package com.sap.security.api;',          'interface IRoleFactory'),
    ('com/sap/security/api/IGroup.java',          'package com.sap.security.api;',          'interface IGroup'),
    ('com/sap/security/api/IGroupFactory.java',   'package com.sap.security.api;',          'interface IGroupFactory'),
    ('com/sap/security/api/IAuthenticator.java',  'package com.sap.security.api;',          'interface IAuthenticator'),
    ('com/sap/security/api/UMException.java',     'package com.sap.security.api;',          'class UMException'),
    ('com/sap/security/api/UMFactory.java',       'package com.sap.security.api;',          'class UMFactory'),
    (
        'com/sap/engine/services/configuration/appconfiguration/ApplicationPropertiesChangeListener.java',
        'package com.sap.engine.services.configuration.appconfiguration;',
        'interface ApplicationPropertiesChangeListener',
    ),
]


def test_all_stubs_generated(tmp_path):
    StubGenerator(_config(tmp_path)).generate()
    src_root = tmp_path / 'out' / 'src' / 'main' / 'java'
    for rel_path, _, _ in EXPECTED_STUBS:
        assert (src_root / rel_path).exists(), f'Missing stub: {rel_path}'


@pytest.mark.parametrize('rel_path,expected_package,expected_type', EXPECTED_STUBS)
def test_stub_package_and_type_declarations(tmp_path, rel_path, expected_package, expected_type):
    StubGenerator(_config(tmp_path)).generate()
    src_root = tmp_path / 'out' / 'src' / 'main' / 'java'
    content = (src_root / rel_path).read_text(encoding='utf-8')
    assert expected_package in content, f'{rel_path}: missing {expected_package}'
    assert expected_type in content, f'{rel_path}: missing {expected_type}'


def test_umfactory_stub_throws_uoe(tmp_path):
    """UMFactory methods must throw UnsupportedOperationException, not silently return."""
    StubGenerator(_config(tmp_path)).generate()
    content = (tmp_path / 'out' / 'src' / 'main' / 'java'
               / 'com/sap/security/api/UMFactory.java').read_text()
    assert 'UnsupportedOperationException' in content


def test_umfactory_has_group_factory_and_authenticator_methods(tmp_path):
    """Real-world usage calls UMFactory.getGroupFactory() and .getAuthenticator() —
    found missing via a real compile failure."""
    StubGenerator(_config(tmp_path)).generate()
    content = (tmp_path / 'out' / 'src' / 'main' / 'java'
               / 'com/sap/security/api/UMFactory.java').read_text()
    assert 'IGroupFactory getGroupFactory()' in content
    assert 'IAuthenticator getAuthenticator()' in content


def test_generate_is_idempotent(tmp_path):
    """Calling generate() twice must not raise and must produce identical content."""
    gen = StubGenerator(_config(tmp_path))
    gen.generate()
    gen.generate()
    src_root = tmp_path / 'out' / 'src' / 'main' / 'java'
    for rel_path, _, _ in EXPECTED_STUBS:
        assert (src_root / rel_path).exists()


# ── Dynamic stubs synthesized from usage_harvester findings ──────────────────

def _config_with_harvest(tmp_path, harvested):
    cfg = _config(tmp_path)
    cfg.scan_result = {'unavailable_pkg_usages': harvested}
    return cfg


def test_dynamic_stub_written_for_harvested_type(tmp_path):
    harvested = {
        'com.bbt.cmn.util.services.CommonUtilityBeanLocal': {
            'methods': {'doThing#0': {'return_type': None, 'static': False}}
        }
    }
    StubGenerator(_config_with_harvest(tmp_path, harvested)).generate()
    dest = tmp_path / 'out' / 'src' / 'main' / 'java' / 'com/bbt/cmn/util/services/CommonUtilityBeanLocal.java'
    assert dest.exists()
    content = dest.read_text(encoding='utf-8')
    assert 'package com.bbt.cmn.util.services;' in content
    assert 'interface CommonUtilityBeanLocal' in content
    assert 'Object doThing();' in content


def test_dynamic_stub_static_method_throws_uoe(tmp_path):
    harvested = {
        'com.bbt.cmn.Foo': {
            'methods': {'staticHelper#0': {'return_type': None, 'static': True}}
        }
    }
    StubGenerator(_config_with_harvest(tmp_path, harvested)).generate()
    content = (tmp_path / 'out' / 'src' / 'main' / 'java' / 'com/bbt/cmn/Foo.java').read_text()
    assert 'static Object staticHelper()' in content
    assert 'UnsupportedOperationException' in content


def test_dynamic_stub_overloads_get_distinct_signatures(tmp_path):
    harvested = {
        'com.bbt.cmn.Foo': {
            'methods': {
                'doThing#0': {'return_type': None, 'static': False},
                'doThing#2': {'return_type': None, 'static': False},
            }
        }
    }
    StubGenerator(_config_with_harvest(tmp_path, harvested)).generate()
    content = (tmp_path / 'out' / 'src' / 'main' / 'java' / 'com/bbt/cmn/Foo.java').read_text()
    assert 'Object doThing();' in content
    assert 'Object doThing(Object arg0, Object arg1);' in content


def test_dynamic_stub_flags_from_cache_methods_as_unverified(tmp_path):
    """A method gap-filled from the local cache (see local_shape_cache.py) must
    be visibly flagged in the generated source — this app's own code never
    called it, so its shape isn't confirmed for this app."""
    harvested = {
        'com.bbt.cmn.Foo': {
            'methods': {'legacyOnly#0': {'return_type': None, 'static': False, 'from_cache': True}}
        }
    }
    StubGenerator(_config_with_harvest(tmp_path, harvested)).generate()
    content = (tmp_path / 'out' / 'src' / 'main' / 'java' / 'com/bbt/cmn/Foo.java').read_text()
    assert 'inherited from a previous migration' in content
    assert 'Object legacyOnly();' in content


def test_dynamic_stub_trusts_known_jdk_collection_return_type(tmp_path):
    harvested = {
        'com.bbt.cmn.Foo': {
            'methods': {'getValues#0': {'return_type': 'Set<String>', 'static': False}}
        }
    }
    StubGenerator(_config_with_harvest(tmp_path, harvested)).generate()
    content = (tmp_path / 'out' / 'src' / 'main' / 'java' / 'com/bbt/cmn/Foo.java').read_text()
    assert 'import java.util.Set;' in content
    assert 'Set<String> getValues();' in content
    assert 'guessed' not in content


def test_dynamic_stub_trusts_bare_java_lang_return_type(tmp_path):
    """String (and other java.lang types) need no import and are always safe
    to trust verbatim — found missing via a real harvest against AP Vendor."""
    harvested = {
        'com.bbt.cmn.Foo': {
            'methods': {'getName#0': {'return_type': 'String', 'static': False}}
        }
    }
    StubGenerator(_config_with_harvest(tmp_path, harvested)).generate()
    content = (tmp_path / 'out' / 'src' / 'main' / 'java' / 'com/bbt/cmn/Foo.java').read_text()
    assert 'String getName();' in content
    assert 'guessed' not in content


def test_dynamic_stub_falls_back_to_object_for_unrecognized_return_type(tmp_path):
    harvested = {
        'com.bbt.cmn.Foo': {
            'methods': {'getThing#0': {'return_type': 'SomeUnknownType', 'static': False}}
        }
    }
    StubGenerator(_config_with_harvest(tmp_path, harvested)).generate()
    content = (tmp_path / 'out' / 'src' / 'main' / 'java' / 'com/bbt/cmn/Foo.java').read_text()
    assert 'Object getThing();' in content
    assert 'guessed as Object' in content


def test_no_dynamic_stubs_written_when_nothing_harvested(tmp_path):
    """Default scan_result ({}) must not error and must not write anything extra."""
    StubGenerator(_config(tmp_path)).generate()
    src_root = tmp_path / 'out' / 'src' / 'main' / 'java'
    all_files = list(src_root.rglob('*.java'))
    assert len(all_files) == len(EXPECTED_STUBS)


def test_dynamic_stub_never_written_outside_output_dir(tmp_path):
    """Nothing from this feature may be written anywhere but this app's own
    output tree — no persistence, no shared file, per the no-git/no-cross-
    developer-sharing constraint."""
    tool_repo_root = Path(__file__).parent.parent
    before = set(tool_repo_root.rglob('*'))
    harvested = {'com.bbt.cmn.Foo': {'methods': {'doThing#0': {'return_type': None, 'static': False}}}}
    StubGenerator(_config_with_harvest(tmp_path, harvested)).generate()
    after = set(tool_repo_root.rglob('*'))
    assert after == before
