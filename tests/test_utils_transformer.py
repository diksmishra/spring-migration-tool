"""Tests for UtilsTransformer — focuses on implements clause removal."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pathlib import Path
import pytest
from migration_tool.config import MigrationConfig
from migration_tool.transformers.utils_transformer import UtilsTransformer


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


def transform(source, tmp_path):
    cfg = _config(tmp_path)
    t = UtilsTransformer(cfg)
    result, todos = t.transform(source, Path('Foo.java'), {})
    return result, todos


# ── ApplicationPropertiesChangeListener removal ────────────────────────────────

def test_removes_only_interface_in_implements(tmp_path):
    """implements ApplicationPropertiesChangeListener { → no implements clause."""
    src = 'public class Foo implements ApplicationPropertiesChangeListener {\n}\n'
    result, _ = transform(src, tmp_path)
    assert 'ApplicationPropertiesChangeListener' not in result
    assert 'implements' not in result


def test_removes_first_of_multiple_implements(tmp_path):
    """implements ApplicationPropertiesChangeListener, Serializable → implements Serializable."""
    src = 'public class Foo implements ApplicationPropertiesChangeListener, Serializable {\n}\n'
    result, _ = transform(src, tmp_path)
    assert 'ApplicationPropertiesChangeListener' not in result
    assert 'implements Serializable' in result


def test_removes_last_of_multiple_implements(tmp_path):
    """implements Runnable, ApplicationPropertiesChangeListener → implements Runnable."""
    src = 'public class Foo implements Runnable, ApplicationPropertiesChangeListener {\n}\n'
    result, _ = transform(src, tmp_path)
    assert 'ApplicationPropertiesChangeListener' not in result
    assert 'implements Runnable' in result


def test_removes_middle_of_multiple_implements(tmp_path):
    """implements Runnable, ApplicationPropertiesChangeListener, Serializable → Runnable + Serializable."""
    src = 'public class Foo implements Runnable, ApplicationPropertiesChangeListener, Serializable {\n}\n'
    result, _ = transform(src, tmp_path)
    assert 'ApplicationPropertiesChangeListener' not in result
    assert 'Runnable' in result
    assert 'Serializable' in result


def test_no_change_when_no_sap_interface(tmp_path):
    src = 'public class Foo implements Serializable {\n}\n'
    result, _ = transform(src, tmp_path)
    assert result == src


# ── SAP platform API detection ────────────────────────────────────────────────

def test_detects_sap_engine_import(tmp_path):
    src = 'import com.sap.engine.services.configuration.ApplicationPropertiesHandler;\npublic class Foo {}\n'
    _, todos = transform(src, tmp_path)
    assert any('SAP Platform API' in t for t in todos)


# ── Java version deprecation detection ───────────────────────────────────────

def test_detects_new_integer_constructor(tmp_path):
    src = 'public class Foo { Integer i = new Integer(5); }\n'
    _, todos = transform(src, tmp_path)
    assert any('Boxed-type constructors' in t for t in todos)


def test_detects_finalize_method(tmp_path):
    src = 'public class Foo { protected void finalize() {} }\n'
    _, todos = transform(src, tmp_path)
    assert any('finalize' in t for t in todos)


def test_detects_javax_jws_import(tmp_path):
    src = 'import javax.jws.WebService;\n@WebService\npublic class Foo {}\n'
    _, todos = transform(src, tmp_path)
    assert any('JAX-WS' in t for t in todos)
