"""Tests for PersistenceTransformer."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pathlib import Path
from migration_tool.config import MigrationConfig
from migration_tool.transformers.persistence_transformer import PersistenceTransformer


def _config(tmp_path, persistence_mode='jpa'):
    return MigrationConfig(
        source_dir=tmp_path / 'src',
        output_dir=tmp_path / 'out',
        base_package='com.example',
        group_id='com.example',
        artifact_id='test-app',
        spring_boot_version='3.2.5',
        java_version='17',
        persistence_mode=persistence_mode,
    )


def transform(source, tmp_path, persistence_mode='jpa', file_name='Foo.java'):
    cfg = _config(tmp_path, persistence_mode)
    t = PersistenceTransformer(cfg)
    result, todos = t.transform(source, Path(file_name), {})
    return result, todos


# ── javax → jakarta rewrites ──────────────────────────────────────────────────

def test_rewrites_javax_persistence(tmp_path):
    src = 'import javax.persistence.Entity;\n@javax.persistence.Entity\npublic class Foo {}\n'
    result, _ = transform(src, tmp_path)
    assert 'jakarta.persistence.Entity' in result
    assert 'javax.persistence' not in result


def test_rewrites_javax_annotation(tmp_path):
    """jakarta.annotation-api is a real, available dependency — this is a genuine fix, not a flag."""
    src = 'import javax.annotation.PostConstruct;\npublic class Foo {\n    @PostConstruct\n    void init() {}\n}\n'
    result, _ = transform(src, tmp_path)
    assert 'import jakarta.annotation.PostConstruct;' in result
    assert 'javax.annotation' not in result


def test_javax_annotation_alone_triggers_rewrite_pass(tmp_path):
    """A file with only javax.annotation (no persistence/transaction/validation/servlet)
    must still trigger the rewrite — the gating condition must include it."""
    src = 'import javax.annotation.Resource;\npublic class Foo {\n    @Resource\n    Object dep;\n}\n'
    result, _ = transform(src, tmp_path)
    assert 'jakarta.annotation.Resource' in result


def test_no_op_when_no_javax_namespaces_present(tmp_path):
    src = 'public class Foo {}\n'
    result, _ = transform(src, tmp_path)
    assert result == src


# ── OpenJPA import removal ────────────────────────────────────────────────────

def test_removes_openjpa_imports(tmp_path):
    src = 'import org.apache.openjpa.persistence.jdbc.Index;\npublic class Foo {}\n'
    result, _ = transform(src, tmp_path)
    assert 'org.apache.openjpa' not in result


# ── JNDI lookup flagging ──────────────────────────────────────────────────────

def test_flags_jndi_lookup(tmp_path):
    src = 'public class Foo { void m() { new InitialContext(); } }\n'
    _, todos = transform(src, tmp_path)
    assert any('JNDI' in t for t in todos)


def test_no_jndi_flag_when_absent(tmp_path):
    src = 'public class Foo {}\n'
    _, todos = transform(src, tmp_path)
    assert not any('JNDI' in t for t in todos)


# ── sap persistence mode: DAO-file flagging ───────────────────────────────────

def test_sap_mode_flags_dao_file(tmp_path):
    _, todos = transform('public class Foo {}\n', tmp_path, persistence_mode='sap', file_name='FooDAOImpl.java')
    assert any('DAO/persistence class' in t for t in todos)


def test_sap_mode_does_not_flag_non_dao_file(tmp_path):
    _, todos = transform('public class Foo {}\n', tmp_path, persistence_mode='sap', file_name='FooController.java')
    assert not any('DAO/persistence class' in t for t in todos)


def test_jpa_mode_does_not_flag_dao_file(tmp_path):
    """The DAO-flagging is specific to sap mode, not jpa/jdbc."""
    _, todos = transform('public class Foo {}\n', tmp_path, persistence_mode='jpa', file_name='FooDAOImpl.java')
    assert not any('DAO/persistence class' in t for t in todos)
