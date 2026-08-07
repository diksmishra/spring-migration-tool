"""Tests for ImportTransformer."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pathlib import Path
import pytest
from migration_tool.config import MigrationConfig
from migration_tool.transformers.import_transformer import ImportTransformer


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
    t = ImportTransformer(cfg)
    result, todos = t.transform(source, Path('Foo.java'), {})
    return result, todos


# ── @EJB annotation replacement ───────────────────────────────────────────────

def test_ejb_plain_replaced_with_autowired(tmp_path):
    src = 'import javax.ejb.EJB;\npublic class Foo { @EJB MyBean bean; }\n'
    result, _ = transform(src, tmp_path)
    assert '@Autowired' in result
    assert '@EJB' not in result


def test_ejb_with_mapped_name_attribute_stripped(tmp_path):
    """@EJB(mappedName="...") must become @Autowired with no attributes."""
    src = (
        'import javax.ejb.EJB;\n'
        'public class Foo {\n'
        '    @EJB(mappedName="ejb/MyBean")\n'
        '    private MyBean bean;\n'
        '}\n'
    )
    result, _ = transform(src, tmp_path)
    assert '@Autowired' in result
    assert 'mappedName' not in result
    assert '@EJB' not in result


def test_ejb_with_multiple_attributes_stripped(tmp_path):
    src = (
        'import javax.ejb.EJB;\n'
        'public class Foo {\n'
        '    @EJB(name="myBean", beanName="MyBeanImpl")\n'
        '    private MyBean bean;\n'
        '}\n'
    )
    result, _ = transform(src, tmp_path)
    assert '@Autowired' in result
    assert 'name=' not in result.split('@Autowired')[1].split('\n')[0]


# ── @Stateless / @Stateful replacement ───────────────────────────────────────

def test_stateless_becomes_service(tmp_path):
    src = 'import javax.ejb.Stateless;\n@Stateless\npublic class Foo {}\n'
    result, _ = transform(src, tmp_path)
    assert '@Service' in result
    assert '@Stateless' not in result


def test_stateful_becomes_service(tmp_path):
    src = 'import javax.ejb.Stateful;\n@Stateful\npublic class Foo {}\n'
    result, _ = transform(src, tmp_path)
    assert '@Service' in result
    assert '@Stateful' not in result


# ── com.sap.engine.* commented out ───────────────────────────────────────────

def test_sap_engine_import_commented_out(tmp_path):
    src = 'import com.sap.engine.services.configuration.appconfiguration.ApplicationPropertiesHandler;\npublic class Foo {}\n'
    result, todos = transform(src, tmp_path)
    assert '// import com.sap.engine' in result
    assert '// TODO MANUAL' in result
    assert any('com.sap.engine' in t for t in todos)


# ── com.sap.security.api.* NOT commented out (stubs handle it) ───────────────

def test_sap_security_api_import_kept(tmp_path):
    """Security API imports must remain intact — stub classes handle compilation."""
    src = 'import com.sap.security.api.UMFactory;\nimport com.sap.security.api.IUser;\npublic class Foo {}\n'
    result, _ = transform(src, tmp_path)
    assert 'import com.sap.security.api.UMFactory;' in result
    assert 'import com.sap.security.api.IUser;' in result
    assert '// import com.sap.security.api' not in result


# ── EJB import replacement ────────────────────────────────────────────────────

def test_ejb_import_replaced_with_autowired_import(tmp_path):
    src = 'import javax.ejb.EJB;\npublic class Foo {}\n'
    result, _ = transform(src, tmp_path)
    assert 'import org.springframework.beans.factory.annotation.Autowired;' in result
    assert 'import javax.ejb.EJB;' not in result


def test_stateless_import_removed(tmp_path):
    src = 'import javax.ejb.Stateless;\n@Stateless\npublic class Foo {}\n'
    result, _ = transform(src, tmp_path)
    assert 'import javax.ejb.Stateless;' not in result
