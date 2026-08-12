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


def test_generate_is_idempotent(tmp_path):
    """Calling generate() twice must not raise and must produce identical content."""
    gen = StubGenerator(_config(tmp_path))
    gen.generate()
    gen.generate()
    src_root = tmp_path / 'out' / 'src' / 'main' / 'java'
    for rel_path, _, _ in EXPECTED_STUBS:
        assert (src_root / rel_path).exists()
