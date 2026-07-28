import re
from pathlib import Path
from typing import Tuple, List

from migration_tool.config import MigrationConfig

# SAP-specific imports that should be fully removed or flagged
SAP_IMPORTS_REMOVE = [
    # Already handled by logging transformer, but catch any remaining
    re.compile(r'^import\s+com\.sap\.tc\.logging\.[^;]+;\s*\n', re.MULTILINE),
]

SAP_IMPORTS_FLAG = {
    re.compile(r'^import\s+com\.sap\.security\.[^;]+;', re.MULTILINE):
        'SAP UME security — replace with Spring Security',
    re.compile(r'^import\s+com\.sap\.conn\.jco\.[^;]+;', re.MULTILINE):
        'SAP JCo (Java Connector) — requires library replacement',
    re.compile(r'^import\s+com\.sap\.mw\.jco\.[^;]+;', re.MULTILINE):
        'SAP JCo (Java Connector) — requires library replacement',
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
    (re.compile(r'@EJB\b'), '@Autowired'),
]


class ImportTransformer:
    def __init__(self, config: MigrationConfig):
        self.config = config

    def transform(self, source: str, file_path: Path, scan_result: dict) -> Tuple[str, List[str]]:
        todos = []

        # Remove known-bad SAP imports
        for pattern in SAP_IMPORTS_REMOVE:
            source = pattern.sub('', source)

        # Flag SAP imports that need manual work
        for pattern, message in SAP_IMPORTS_FLAG.items():
            if pattern.search(source):
                todos.append(f'MANUAL: {message}')

        # Replace EJB annotations/imports with Spring equivalents
        for old, new in EJB_REPLACEMENTS:
            source = old.sub(new, source)

        return source, todos
