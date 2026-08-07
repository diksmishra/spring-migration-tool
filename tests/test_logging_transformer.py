"""Tests for LoggingTransformer."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pathlib import Path
import pytest
from migration_tool.config import MigrationConfig
from migration_tool.transformers.logging_transformer import LoggingTransformer


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
    t = LoggingTransformer(cfg)
    result, _ = t.transform(source, Path('Foo.java'), {})
    return result


# ── No-op when no SAP logging ─────────────────────────────────────────────────

def test_no_op_when_no_sap_logging(tmp_path):
    src = 'package com.example;\npublic class Foo {}\n'
    assert transform(src, tmp_path) == src


# ── LOCATION_FIELD removal ─────────────────────────────────────────────────────

def test_removes_static_final_location_field(tmp_path):
    src = (
        'import com.sap.tc.logging.Location;\n'
        'public class Foo {\n'
        '    private static final Location location = Location.getLocation(Foo.class);\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    assert 'Location location' not in result
    assert 'Location.getLocation' not in result


def test_removes_non_static_location_field(tmp_path):
    src = (
        'import com.sap.tc.logging.Location;\n'
        'public class Bar {\n'
        '    private Location loc = Location.getLocation(Bar.class);\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    assert 'Location loc' not in result


def test_removes_location_field_with_this(tmp_path):
    src = (
        'import com.sap.tc.logging.Location;\n'
        'public class Baz {\n'
        '    private static Location LOCATION = Location.getLocation(this);\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    assert 'Location LOCATION' not in result


# ── SimpleLogger.trace conversion ─────────────────────────────────────────────

def test_converts_simple_logger_trace_info(tmp_path):
    src = (
        'import com.sap.tc.logging.SimpleLogger;\n'
        'import com.sap.tc.logging.Severity;\n'
        'public class Foo {\n'
        '    void m() { SimpleLogger.trace(Severity.INFO, loc, "hello world"); }\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    assert 'log.info("hello world")' in result
    assert 'SimpleLogger.trace' not in result


def test_converts_simple_logger_trace_error(tmp_path):
    src = (
        'import com.sap.tc.logging.SimpleLogger;\n'
        'import com.sap.tc.logging.Severity;\n'
        'public class Foo {\n'
        '    void m() { SimpleLogger.trace(Severity.ERROR, location, "bad: " + msg); }\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    assert 'log.error("bad: " + msg)' in result


def test_converts_simple_logger_trace_warning(tmp_path):
    src = (
        'import com.sap.tc.logging.SimpleLogger;\n'
        'import com.sap.tc.logging.Severity;\n'
        'public class Foo {\n'
        '    void m() { SimpleLogger.trace(Severity.WARNING, loc, msg); }\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    assert 'log.warn(msg)' in result


def test_converts_simple_logger_trace_4arg_form(tmp_path):
    """4-arg form (extra param) should also be converted, dropping the extra arg."""
    src = (
        'import com.sap.tc.logging.SimpleLogger;\n'
        'import com.sap.tc.logging.Severity;\n'
        'public class Foo {\n'
        '    void m() { SimpleLogger.trace(Severity.DEBUG, loc, "msg", extraArg); }\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    assert 'log.debug("msg")' in result
    assert 'SimpleLogger.trace' not in result


# ── SimpleLogger.traceThrowable conversion ────────────────────────────────────

def test_converts_simple_logger_trace_throwable(tmp_path):
    src = (
        'import com.sap.tc.logging.SimpleLogger;\n'
        'import com.sap.tc.logging.Severity;\n'
        'public class Foo {\n'
        '    void m(Exception e) { SimpleLogger.traceThrowable(Severity.ERROR, loc, "fail", e); }\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    assert 'log.error("fail", e)' in result
    assert 'SimpleLogger.traceThrowable' not in result


# ── Catch-all for unmatched SimpleLogger calls ────────────────────────────────

def test_catch_all_comments_out_unmatched_simple_logger(tmp_path):
    """SimpleLogger forms the regexes can't handle should be commented out with a TODO."""
    src = (
        'import com.sap.tc.logging.SimpleLogger;\n'
        'import com.sap.tc.logging.Severity;\n'
        'public class Foo {\n'
        '    void m() { SimpleLogger.writeFatal(Severity.FATAL, loc, "die"); }\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    # The call must be commented out (no active line contains it)
    active_lines = [l for l in result.split('\n') if not l.lstrip().startswith('//')]
    assert not any('SimpleLogger.writeFatal' in l for l in active_lines)
    assert '// TODO MANUAL' in result
    assert 'SimpleLogger.writeFatal' in result  # still visible inside the comment


# ── Import injection ──────────────────────────────────────────────────────────

def test_injects_slf4j_imports(tmp_path):
    src = (
        'import com.sap.tc.logging.SimpleLogger;\n'
        'import com.sap.tc.logging.Severity;\n'
        'public class Foo {\n'
        '    void m() { SimpleLogger.trace(Severity.INFO, loc, "hi"); }\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    assert 'import org.slf4j.Logger;' in result
    assert 'import org.slf4j.LoggerFactory;' in result


def test_does_not_double_inject_imports(tmp_path):
    src = (
        'import org.slf4j.Logger;\n'
        'import org.slf4j.LoggerFactory;\n'
        'import com.sap.tc.logging.SimpleLogger;\n'
        'import com.sap.tc.logging.Severity;\n'
        'public class Foo {\n'
        '    void m() { SimpleLogger.trace(Severity.INFO, loc, "hi"); }\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    assert result.count('import org.slf4j.Logger;') == 1


# ── Logger field injection ────────────────────────────────────────────────────

def test_injects_logger_field_with_class_name(tmp_path):
    src = (
        'import com.sap.tc.logging.SimpleLogger;\n'
        'import com.sap.tc.logging.Severity;\n'
        'public class MyService {\n'
        '    void m() { SimpleLogger.trace(Severity.INFO, loc, "hi"); }\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    assert 'LoggerFactory.getLogger(MyService.class)' in result


def test_does_not_double_inject_logger_field(tmp_path):
    src = (
        'import org.slf4j.Logger;\n'
        'import org.slf4j.LoggerFactory;\n'
        'import com.sap.tc.logging.SimpleLogger;\n'
        'import com.sap.tc.logging.Severity;\n'
        'public class Foo {\n'
        '    private static final Logger log = LoggerFactory.getLogger(Foo.class);\n'
        '    void m() { SimpleLogger.trace(Severity.INFO, loc, "hi"); }\n'
        '}\n'
    )
    result = transform(src, tmp_path)
    assert result.count('LoggerFactory.getLogger') == 1
