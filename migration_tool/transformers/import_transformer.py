import re
from pathlib import Path
from typing import Tuple, List

from migration_tool.config import MigrationConfig

# SAP-specific imports that should be fully removed or flagged
SAP_IMPORTS_REMOVE = [
    # Already handled by logging transformer, but catch any remaining
    re.compile(r'^import\s+com\.sap\.tc\.logging\.[^;]+;\s*\n', re.MULTILINE),
]

# SAP imports that must be removed — they reference libraries that do not exist
# on BTP CF / Spring Boot. Keeping them causes compile failures.
# We comment them out with a TODO marker so the developer can see what was there.
# NOTE: com.sap.security.api.* is NOT here — stubs are generated instead so the
# source keeps compiling with those imports intact.
SAP_IMPORTS_REMOVE_WITH_TODO = {
    re.compile(r'^(import\s+com\.sap\.conn\.jco\.[^;]+;)\s*$', re.MULTILINE):
        'SAP JCo (Java Connector) — requires library replacement',
    re.compile(r'^(import\s+com\.sap\.mw\.jco\.[^;]+;)\s*$', re.MULTILINE):
        'SAP JCo (Java Connector) — requires library replacement',
    re.compile(r'^(import\s+com\.sap\.engine\.[^;]+;)\s*$', re.MULTILINE):
        'SAP NetWeaver platform API — replace with Spring Boot equivalent',
}

SAP_IMPORTS_FLAG = {
    re.compile(r'^import\s+javax\.naming\.[^;]+;', re.MULTILINE):
        'JNDI usage — replace with Spring DataSource injection',
    re.compile(r'^import\s+javax\.ejb\.[^;]+;', re.MULTILINE):
        'EJB annotation — see EJB migration below',
}

# EJB annotations to replace
EJB_REPLACEMENTS = [
    (re.compile(r'^import\s+javax\.ejb\.Stateless;\s*\n', re.MULTILINE), ''),
    (re.compile(r'^import\s+javax\.ejb\.Stateful;\s*\n', re.MULTILINE), ''),
    (re.compile(r'^import\s+javax\.ejb\.EJB;\s*\n', re.MULTILINE),
     'import org.springframework.beans.factory.annotation.Autowired;\n'),
    (re.compile(r'@Stateless\b'), '@Service'),
    (re.compile(r'@Stateful\b'), '@Service'),
    # Strip all @EJB attributes (e.g. mappedName="...") — @Autowired accepts none
    (re.compile(r'@EJB\s*(?:\([^)]*\))?'), '@Autowired'),
]


class ImportTransformer:
    def __init__(self, config: MigrationConfig):
        self.config = config

    def transform(self, source: str, file_path: Path, scan_result: dict) -> Tuple[str, List[str]]:
        todos = []

        # Remove known-bad SAP imports (logging — already handled by LoggingTransformer)
        for pattern in SAP_IMPORTS_REMOVE:
            source = pattern.sub('', source)

        # Comment out SAP imports that have no Spring Boot equivalent.
        # Keeping them causes compile failures; commenting preserves traceability.
        # One todos entry is added per matched import line so the report has 1:1
        # coverage with every // TODO MANUAL comment inserted into source.
        for pattern, message in SAP_IMPORTS_REMOVE_WITH_TODO.items():
            matches = pattern.findall(source)  # captured group = the import line
            if matches:
                def _comment_out(m, msg=message):
                    return f'// TODO MANUAL — {msg}\n// {m.group(1)}'
                source = pattern.sub(_comment_out, source)
                for import_line in matches:
                    todos.append(f'MANUAL: {message} — `{import_line.strip()}`')

        # Flag (but keep) SAP imports that need manual work but may compile
        for pattern, message in SAP_IMPORTS_FLAG.items():
            if pattern.search(source):
                todos.append(f'MANUAL: {message}')

        # Replace EJB annotations/imports with Spring equivalents
        for old, new in EJB_REPLACEMENTS:
            source = old.sub(new, source)

        return source, todos
