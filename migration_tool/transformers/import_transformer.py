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
    re.compile(r'^(import\s+com\.sap\.bpm\.[^;]+;)\s*$', re.MULTILINE):
        'SAP BPM workflow API — being replaced by Build Process Automation (BPA) on BTP; no direct Spring Boot equivalent',
    re.compile(r'^(import\s+com\.sap\.scheduler\.[^;]+;)\s*$', re.MULTILINE):
        'SAP NetWeaver Job Scheduler / MDB framework — no Spring Boot equivalent; rewrite as a Spring @Scheduled task or @JmsListener',
    re.compile(r'^(import\s+javax\.resource\.cci\.[^;]+;)\s*$', re.MULTILINE):
        'JCA Connector Architecture (CCI) — SAP RFC/BAPI-style resource adapter with no Spring Boot equivalent; '
        'replace with SAP JCo standalone or expose SAP via REST',
}

SAP_IMPORTS_FLAG = {
    re.compile(r'^import\s+javax\.naming\.[^;]+;', re.MULTILINE):
        'JNDI usage — replace with Spring DataSource injection',
}

# EJB annotations to replace
EJB_REPLACEMENTS = [
    (re.compile(r'^import\s+javax\.ejb\.Stateless;\s*\n', re.MULTILINE), ''),
    (re.compile(r'^import\s+javax\.ejb\.Stateful;\s*\n', re.MULTILINE), ''),
    (re.compile(r'^import\s+javax\.ejb\.EJB;\s*\n', re.MULTILINE),
     'import org.springframework.beans.factory.annotation.Autowired;\n'),
    (re.compile(r'@Stateless\b'), '@Service'),
    (re.compile(r'@Stateful\b'), '@Service'),
    # Strip all @EJB attributes (e.g. mappedName="...") — @Autowired accepts none.
    # The \s* must stay INSIDE the optional group: @EJB is very often on its own
    # line with the field on the next ("@EJB\n\tprivate Foo bar;") — a leading
    # \s* would swallow that whitespace whenever no "(...)" follows, gluing the
    # replacement straight onto the next token ("@Autowiredprivate Foo bar;").
    (re.compile(r'@EJB(?:\s*\([^)]*\))?'), '@Autowired'),
]

# Java EE / EJB-container plumbing left after the Stateless/Stateful/EJB→Spring
# swap above — MessageDriven, ActivationConfigProperty, Local, TransactionManagement,
# interceptors, etc. Spring Boot doesn't run inside an EJB container, so none of
# this has a direct equivalent. Must run AFTER EJB_REPLACEMENTS so the already-
# handled Stateless/Stateful/EJB imports aren't commented out first.
JAVA_EE_CONTAINER_IMPORTS_REMOVE_WITH_TODO = {
    re.compile(r'^(import\s+javax\.ejb\.[^;]+;)\s*$', re.MULTILINE):
        'Java EE / EJB container API — Spring Boot does not run inside an EJB container. '
        'If this is a Message-Driven Bean, rewrite as a Spring @JmsListener or @Scheduled task.',
    re.compile(r'^(import\s+javax\.interceptor\.[^;]+;)\s*$', re.MULTILINE):
        'Java EE interceptor API — no Spring Boot equivalent; use a Spring @Aspect, '
        'or remove if it was only EJB-container plumbing.',
    re.compile(r'^(import\s+org\.springframework\.ejb\.[^;]+;)\s*$', re.MULTILINE):
        'Spring EJB-container integration module — meaningless outside an EJB container; '
        'remove and rely on standard Spring dependency injection.',
}


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
        source, todos = self._comment_out_with_todo(source, todos, SAP_IMPORTS_REMOVE_WITH_TODO)

        # Flag (but keep) SAP imports that need manual work but may compile
        for pattern, message in SAP_IMPORTS_FLAG.items():
            if pattern.search(source):
                todos.append(f'MANUAL: {message}')

        # Replace EJB annotations/imports with Spring equivalents
        for old, new in EJB_REPLACEMENTS:
            source = old.sub(new, source)

        # Comment out any EJB-container plumbing EJB_REPLACEMENTS above didn't
        # know how to convert (MessageDriven, ActivationConfigProperty, Local,
        # TransactionManagement, interceptors, ...). Must run after
        # EJB_REPLACEMENTS so the already-handled imports aren't double-touched.
        source, todos = self._comment_out_with_todo(source, todos, JAVA_EE_CONTAINER_IMPORTS_REMOVE_WITH_TODO)

        # Internal/proprietary packages supplied per-run (e.g. a client's own
        # utility packages) — not hardcoded, since this tool stays client-agnostic.
        # See --unavailable-packages.
        for prefix in self.config.unavailable_packages:
            pattern = re.compile(
                r'^(import\s+' + re.escape(prefix) + r'[^;]*;)\s*$', re.MULTILINE
            )
            message = (
                f'Internal/proprietary import ({prefix}) — not available in the target '
                'environment; replace with a Spring Boot equivalent, or vendor the dependency if it must be kept.'
            )
            source, todos = self._comment_out_with_todo(source, todos, {pattern: message})

        return source, todos

    @staticmethod
    def _comment_out_with_todo(source: str, todos: List[str], patterns: dict) -> Tuple[str, List[str]]:
        """Comment out every import matching a pattern with a // TODO MANUAL marker.

        One todos entry is added per matched import line so the report has a 1:1
        relationship with every // TODO MANUAL comment inserted into source.
        """
        for pattern, message in patterns.items():
            matches = pattern.findall(source)  # captured group = the import line
            if matches:
                def _comment_out(m, msg=message):
                    return f'// TODO MANUAL — {msg}\n// {m.group(1)}'
                source = pattern.sub(_comment_out, source)
                for import_line in matches:
                    todos.append(f'MANUAL: {message} — `{import_line.strip()}`')
        return source, todos
