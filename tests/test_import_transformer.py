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


def transform(source, tmp_path, unavailable_packages=None):
    cfg = _config(tmp_path)
    if unavailable_packages:
        cfg.unavailable_packages = unavailable_packages
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


def test_ejb_on_own_line_keeps_whitespace_before_field(tmp_path):
    """@EJB on its own line, field on the next, must not glue into '@Autowiredprivate'."""
    src = (
        'import javax.ejb.EJB;\n'
        'public class Foo {\n'
        '\t@EJB\n'
        '\tprivate MyBean bean;\n'
        '}\n'
    )
    result, _ = transform(src, tmp_path)
    assert '@Autowiredprivate' not in result
    assert '@Autowired\n\tprivate MyBean bean;' in result


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


# ── com.sap.bpm.* / com.sap.scheduler.* commented out ────────────────────────

def test_sap_bpm_import_commented_out(tmp_path):
    src = 'import com.sap.bpm.tm.api.TaskDetail;\npublic class Foo {}\n'
    result, todos = transform(src, tmp_path)
    assert '// import com.sap.bpm' in result
    assert '// TODO MANUAL' in result
    assert any('com.sap.bpm' in t and 'Build Process Automation' in t for t in todos)


def test_sap_scheduler_import_commented_out(tmp_path):
    src = 'import com.sap.scheduler.runtime.mdb.MDBJobImplementation;\npublic class Foo {}\n'
    result, todos = transform(src, tmp_path)
    assert '// import com.sap.scheduler' in result
    assert any('com.sap.scheduler' in t for t in todos)


def test_javax_resource_cci_import_commented_out(tmp_path):
    src = 'import javax.resource.cci.Connection;\npublic class Foo {}\n'
    result, todos = transform(src, tmp_path)
    assert '// import javax.resource.cci' in result
    assert any('JCA' in t for t in todos)


# ── Remaining EJB-container plumbing (after Stateless/Stateful/EJB→Spring) ───

def test_message_driven_import_commented_out(tmp_path):
    src = 'import javax.ejb.MessageDriven;\n@MessageDriven\npublic class Foo {}\n'
    result, todos = transform(src, tmp_path)
    assert '// import javax.ejb.MessageDriven' in result
    assert any('EJB container' in t for t in todos)


def test_javax_interceptor_import_commented_out(tmp_path):
    src = 'import javax.interceptor.Interceptors;\npublic class Foo {}\n'
    result, todos = transform(src, tmp_path)
    assert '// import javax.interceptor.Interceptors' in result


def test_spring_ejb_interceptor_import_commented_out(tmp_path):
    src = 'import org.springframework.ejb.interceptor.SpringBeanAutowiringInterceptor;\npublic class Foo {}\n'
    result, todos = transform(src, tmp_path)
    assert '// import org.springframework.ejb.interceptor' in result


def test_javax_jws_import_commented_out(tmp_path):
    """javax.jws (JAX-WS) doesn't exist on the JDK or in Spring Boot — must be
    commented out, not just flagged, or "package does not exist" persists."""
    src = 'import javax.jws.WebService;\n@WebService\npublic class Foo {}\n'
    result, todos = transform(src, tmp_path)
    assert '// import javax.jws.WebService' in result
    assert any('JAX-WS' in t for t in todos)


def test_ejb_conversion_still_works_alongside_container_plumbing_removal(tmp_path):
    """The Stateless/Stateful/EJB→Spring swap must still fire even though the
    broader javax.ejb.* comment-out now runs right after it."""
    src = (
        'import javax.ejb.EJB;\n'
        'import javax.ejb.MessageDriven;\n'
        'public class Foo { @EJB MyBean bean; }\n'
    )
    result, _ = transform(src, tmp_path)
    assert 'import org.springframework.beans.factory.annotation.Autowired;' in result
    assert '@Autowired' in result
    assert 'import javax.ejb.EJB;' not in result
    assert '// import javax.ejb.EJB;' not in result  # must not be double-commented
    assert '// import javax.ejb.MessageDriven' in result


# ── Generic --unavailable-packages mechanism ─────────────────────────────────

def test_unavailable_packages_commented_out_when_supplied(tmp_path):
    src = 'import com.bbt.cmn.util.services.CommonUtilityBeanLocal;\npublic class Foo {}\n'
    result, todos = transform(src, tmp_path, unavailable_packages=['com.bbt.cmn'])
    assert '// import com.bbt.cmn.util.services.CommonUtilityBeanLocal;' in result
    assert '// TODO MANUAL' in result
    assert any('com.bbt.cmn' in t for t in todos)


def test_unavailable_packages_noop_when_not_supplied(tmp_path):
    """No client-specific behavior by default — the tool stays generic."""
    src = 'import com.bbt.cmn.util.services.CommonUtilityBeanLocal;\npublic class Foo {}\n'
    result, todos = transform(src, tmp_path)
    assert 'import com.bbt.cmn.util.services.CommonUtilityBeanLocal;' in result
    assert not any('com.bbt' in t for t in todos)
