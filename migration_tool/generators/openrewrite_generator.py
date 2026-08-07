"""
Generates run-openrewrite.sh — a script that applies OpenRewrite modernization
recipes (Java version upgrade, Jakarta EE migration, Spring Boot version
upgrade, Log4j->SLF4J logging migration, static-analysis cleanup) to the
migrated project.

The script is deliberately not run during migration itself: the source
environment may be air-gapped, while OpenRewrite's Maven plugin needs to
download recipe artifacts from Maven Central. It is meant to be run later,
in a connected environment (e.g. a cloud IDE), before or after resolving the
manual TODO items in the migration report.

The active recipe list is fixed rather than derived from MigrationConfig —
see run-openrewrite.sh.j2 for the recipe set and the reasoning behind their
execution order.
"""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from migration_tool.config import MigrationConfig


class OpenRewriteGenerator:
    def __init__(self, config: MigrationConfig):
        self.config = config

    def generate(self):
        env = Environment(
            loader=FileSystemLoader(
                Path(__file__).parent.parent.parent / 'templates'
            )
        )
        content = env.get_template('run-openrewrite.sh.j2').render()

        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        out = self.config.output_dir / 'run-openrewrite.sh'
        out.write_text(content, encoding='utf-8', newline='\n')
        try:
            out.chmod(0o755)
        except OSError:
            pass
