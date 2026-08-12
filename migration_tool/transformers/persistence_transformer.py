import re
from pathlib import Path
from typing import Tuple, List

from migration_tool.config import MigrationConfig

# javax → jakarta (required for Spring Boot 3.x / Jakarta EE 9+)
JAVAX_TO_JAKARTA = [
    (re.compile(r'\bjavax\.persistence\.'), 'jakarta.persistence.'),
    (re.compile(r'\bjavax\.transaction\.'), 'jakarta.transaction.'),
    (re.compile(r'\bjavax\.validation\.'), 'jakarta.validation.'),
    (re.compile(r'\bjavax\.servlet\.'), 'jakarta.servlet.'),
    # jakarta.annotation-api (@PostConstruct/@PreDestroy/@Resource) is a real,
    # available dependency — Spring Boot pulls it in transitively — so this is
    # a genuine rename, not just a flag like the removed-from-the-JDK cases below.
    (re.compile(r'\bjavax\.annotation\.'), 'jakarta.annotation.'),
]

# JNDI DataSource lookup pattern (flag as TODO)
JNDI_LOOKUP = re.compile(
    r'new\s+InitialContext\(\)|'
    r'context\.lookup\s*\(|'
    r'ctx\.lookup\s*\(',
    re.IGNORECASE
)

# OpenJPA → standard JPA
OPENJPA_IMPORTS = re.compile(
    r'^import\s+org\.apache\.openjpa\.[^;]+;\s*\n', re.MULTILINE
)


class PersistenceTransformer:
    def __init__(self, config: MigrationConfig):
        self.config = config

    def transform(self, source: str, file_path: Path, scan_result: dict) -> Tuple[str, List[str]]:
        todos = []
        mode = self.config.persistence_mode

        # Always: javax → jakarta (Spring Boot 3.x requires this regardless of mode)
        if 'javax.persistence' in source or 'javax.transaction' in source \
                or 'javax.validation' in source or 'javax.servlet' in source \
                or 'javax.annotation' in source:
            for old_pattern, new_text in JAVAX_TO_JAKARTA:
                source = old_pattern.sub(new_text, source)

        # Always: remove OpenJPA-specific imports (standard JPA equivalents work)
        source = OPENJPA_IMPORTS.sub('', source)

        # JNDI lookups — always flag
        if JNDI_LOOKUP.search(source):
            todos.append(
                'MANUAL: JNDI DataSource lookup detected — '
                'replace with @Autowired DataSource or Spring Boot datasource config'
            )

        if mode == 'sap':
            # SAP-proprietary: flag DAO-like files for full manual migration
            file_lower = file_path.name.lower()
            if any(x in file_lower for x in ('dao', 'repo', 'repository', 'persistence', 'data')):
                todos.append(
                    f'MANUAL: {file_path.name} identified as DAO/persistence class — '
                    'full manual migration required for SAP-proprietary persistence'
                )

        return source, todos
