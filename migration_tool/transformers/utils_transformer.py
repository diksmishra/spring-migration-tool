import re
from pathlib import Path
from typing import Tuple, List

from migration_tool.config import MigrationConfig

# ── SAP NetWeaver platform APIs (no Spring Boot equivalent) ──────────────────

SAP_PLATFORM_PATTERNS = {
    re.compile(r'import\s+com\.sap\.engine\.[^;]+;', re.MULTILINE):
        'SAP NetWeaver platform API (com.sap.engine.*) — no Spring Boot equivalent. '
        'Replace com.sap.engine.services.configuration.* with @ConfigurationProperties '
        'or @Value + application.properties. Remove ApplicationPropertiesChangeListener '
        'and replace with @RefreshScope (Spring Cloud Config) if live refresh is needed.',

    re.compile(r'implements\s+[\w\s,]*ApplicationPropertiesChangeListener'):
        'SAP ApplicationPropertiesChangeListener — remove this interface. '
        'Use @RefreshScope + Spring Cloud Config, or @ConfigurationProperties with '
        'a plain properties reload if live config refresh is needed.',
}

# ── Removed or restricted APIs in Java 9–17 ──────────────────────────────────

JAVA_VERSION_PATTERNS = {
    re.compile(r'import\s+javax\.xml\.bind\.[^;]+;', re.MULTILINE):
        'JAXB (javax.xml.bind.*) was removed from the JDK in Java 11. '
        'Add dependency: jakarta.xml.bind:jakarta.xml.bind-api:4.0.0 '
        'and com.sun.xml.bind:jaxb-impl:4.0.4 to pom.xml.',

    re.compile(r'import\s+sun\.[^;]+;', re.MULTILINE):
        'Internal sun.* API — not part of the public JDK contract and may be '
        'inaccessible under Java 17 module restrictions. Replace with standard '
        'java.* equivalents (e.g. sun.misc.BASE64Encoder → java.util.Base64).',

    re.compile(r'import\s+com\.sun\.[^;]+;', re.MULTILINE):
        'Internal com.sun.* API — restricted by the Java module system in Java 9+. '
        'Replace with public JDK or third-party alternatives.',

    re.compile(r'\bSystem\.setSecurityManager\b|\bnew\s+SecurityManager\b'):
        'SecurityManager is deprecated for removal since Java 17 and removed in Java 24. '
        'Remove SecurityManager usage — Spring Security handles application-level '
        'authorization.',

    re.compile(
        r'\bThread\s*\.\s*(?:currentThread\s*\(\s*\)\s*\.)?\s*(?:stop|destroy|suspend|resume)\s*\(',
        re.IGNORECASE
    ):
        'Thread.stop/destroy/suspend/resume are deprecated for removal in Java 17+. '
        'Refactor to cooperative interruption: use Thread.interrupt() and check '
        'Thread.isInterrupted() / InterruptedException.',

    re.compile(
        r'\bnew\s+(?:Integer|Long|Double|Float|Short|Byte|Boolean|Character)\s*\('
    ):
        'Boxed-type constructors (new Integer(), new Long(), etc.) are deprecated for '
        'removal since Java 9. Use the static factory: Integer.valueOf(), Long.valueOf(), '
        'Boolean.valueOf(), etc.',

    re.compile(r'protected\s+(?:void|Object)\s+finalize\s*\(\s*\)'):
        'Object.finalize() is deprecated for removal since Java 9. '
        'Replace with try-with-resources (AutoCloseable) or java.lang.ref.Cleaner.',
}


class UtilsTransformer:
    """
    Detects SAP platform APIs and removed/deprecated Java 9-17 APIs.
    Does not modify source — only produces TODO items for the migration report.
    """

    def __init__(self, config: MigrationConfig):
        self.config = config

    def transform(self, source: str, file_path: Path, scan_result: dict) -> Tuple[str, List[str]]:
        todos = []

        for pattern, message in SAP_PLATFORM_PATTERNS.items():
            if pattern.search(source):
                todos.append(f'MANUAL — SAP Platform API: {message}')

        for pattern, message in JAVA_VERSION_PATTERNS.items():
            if pattern.search(source):
                todos.append(f'MANUAL — Java version upgrade: {message}')

        return source, todos
