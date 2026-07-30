import re
from pathlib import Path
from typing import Tuple, List

from migration_tool.config import MigrationConfig

# SAP import lines to remove
SAP_LOGGING_IMPORTS = [
    re.compile(r'^import\s+com\.sap\.tc\.logging\.Location;\s*\n', re.MULTILINE),
    re.compile(r'^import\s+com\.sap\.tc\.logging\.Severity;\s*\n', re.MULTILINE),
    re.compile(r'^import\s+com\.sap\.tc\.logging\.SimpleLogger;\s*\n', re.MULTILINE),
    re.compile(r'^import\s+com\.sap\.tc\.logging\.\*;\s*\n', re.MULTILINE),
]

# private [static] [final] Location location = Location.getLocation(Foo.class / this);
# Handles: private static final, private static, private final, private (instance field)
LOCATION_FIELD = re.compile(
    r'[ \t]*private\s+(?:static\s+)?(?:final\s+)?Location\s+\w+\s*=\s*'
    r'Location\.getLocation\([^)]+\)\s*;\s*\n'
)

# A Java expression fragment: string literals, concatenations, variable refs, method calls.
# Stops at an unbalanced ')' or ';' so it doesn't bleed into the next statement.
_EXPR = r'(?:[^();,"]|"(?:[^"\\]|\\.)*"|\([^()]*\))+'

# SimpleLogger.traceThrowable(Severity.LEVEL, location, <msg-expr>, <exc-expr>)
SIMPLE_LOGGER_THROWABLE = re.compile(
    r'SimpleLogger\.traceThrowable\(\s*'
    r'Severity\.(\w+)\s*,\s*\w+\s*,\s*'
    r'(' + _EXPR + r')\s*,\s*(\w+)\s*\)',
    re.DOTALL
)

# SimpleLogger.trace(Severity.LEVEL, location, <msg-expr> [, <extra-expr>])
# Handles: simple strings, string concatenations, object variables, 4-arg form
SIMPLE_LOGGER_TRACE = re.compile(
    r'SimpleLogger\.trace\(\s*'
    r'Severity\.(\w+)\s*,\s*\w+\s*,\s*'
    r'(' + _EXPR + r')'
    r'(?:\s*,\s*' + _EXPR + r')?\s*\)',
    re.DOTALL
)

SEVERITY_MAP = {
    'ERROR':   'error',
    'WARNING': 'warn',
    'WARN':    'warn',
    'INFO':    'info',
    'DEBUG':   'debug',
    'PATH':    'trace',
    'ALL':     'trace',
}

SLF4J_IMPORTS = (
    'import org.slf4j.Logger;\n'
    'import org.slf4j.LoggerFactory;\n'
)

# Where to inject the logger field — after class opening brace
CLASS_OPEN = re.compile(r'((?:public\s+)?(?:abstract\s+)?class\s+(\w+)[^{]*\{)')


class LoggingTransformer:
    def __init__(self, config: MigrationConfig):
        self.config = config

    def transform(self, source: str, file_path: Path, scan_result: dict) -> Tuple[str, List[str]]:
        todos = []

        # Only touch files that actually use SAP logging
        if 'com.sap.tc.logging' not in source:
            return source, todos

        # 1. Remove SAP logging imports
        for pattern in SAP_LOGGING_IMPORTS:
            source = pattern.sub('', source)

        # 2. Detect class name for the logger field
        class_match = CLASS_OPEN.search(source)
        class_name = class_match.group(2) if class_match else 'Unknown'

        # 3. Remove Location field
        source = LOCATION_FIELD.sub('', source)

        # 4. Replace SimpleLogger.traceThrowable(...)
        def replace_throwable(m):
            level = SEVERITY_MAP.get(m.group(1).upper(), 'error')
            msg = m.group(2)
            exc = m.group(3)
            return f'log.{level}({msg}, {exc})'
        source = SIMPLE_LOGGER_THROWABLE.sub(replace_throwable, source)

        # 5. Replace SimpleLogger.trace(...)
        def replace_trace(m):
            level = SEVERITY_MAP.get(m.group(1).upper(), 'info')
            msg = m.group(2)
            return f'log.{level}({msg})'
        source = SIMPLE_LOGGER_TRACE.sub(replace_trace, source)

        # 6. Catch-all: comment out any SimpleLogger.* calls that the specific
        #    patterns above didn't match (4-arg forms, complex expressions, etc.)
        if 'SimpleLogger.' in source:
            source = self._comment_out_remaining_simple_logger(source)

        # 7. Inject SLF4J imports after last existing import or after package line
        if 'import org.slf4j.Logger' not in source:
            source = self._inject_imports(source)

        # 8. Inject logger field after class opening brace
        if 'LoggerFactory.getLogger' not in source:
            source = self._inject_logger_field(source, class_name)

        return source, todos

    def _comment_out_remaining_simple_logger(self, source: str) -> str:
        """Comment out any SimpleLogger.* calls not converted by the specific patterns."""
        lines = source.split('\n')
        result = []
        in_multiline = False
        for line in lines:
            stripped = line.lstrip()
            if in_multiline:
                result.append('// ' + line)
                if ';' in line:
                    in_multiline = False
            elif 'SimpleLogger.' in stripped and not stripped.startswith('//'):
                result.append('// TODO MANUAL — SAP logging (not converted): ' + line)
                if ';' not in line:
                    in_multiline = True
            else:
                result.append(line)
        return '\n'.join(result)

    def _inject_imports(self, source: str) -> str:
        """Insert SLF4J imports after the last import statement."""
        last_import = list(re.finditer(r'^import\s+[\w.*]+;\s*$', source, re.MULTILINE))
        if last_import:
            pos = last_import[-1].end()
            return source[:pos] + '\n' + SLF4J_IMPORTS + source[pos:]
        # Fall back: after package declaration
        pkg = re.search(r'^package\s+[\w.]+;\s*$', source, re.MULTILINE)
        if pkg:
            pos = pkg.end()
            return source[:pos] + '\n\n' + SLF4J_IMPORTS + source[pos:]
        return SLF4J_IMPORTS + '\n' + source

    def _inject_logger_field(self, source: str, class_name: str) -> str:
        """Insert the logger field as first member after the class opening brace."""
        m = CLASS_OPEN.search(source)
        if not m:
            return source
        logger_field = (
            f'\n    private static final Logger log = '
            f'LoggerFactory.getLogger({class_name}.class);\n'
        )
        pos = m.end()
        return source[:pos] + logger_field + source[pos:]
