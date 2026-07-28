from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from migration_tool.config import MigrationConfig


class PomGenerator:
    def __init__(self, config: MigrationConfig):
        self.config = config

    def generate(self):
        env = Environment(
            loader=FileSystemLoader(
                Path(__file__).parent.parent.parent / 'templates'
            )
        )
        template = env.get_template('pom.xml.j2')

        mode = self.config.persistence_mode
        content = template.render(
            group_id=self.config.group_id,
            artifact_id=self.config.artifact_id,
            spring_boot_version=self.config.spring_boot_version,
            java_version=self.config.java_version,
            use_jpa=mode == 'jpa',
            use_jdbc=mode == 'jdbc',
            use_hana_cloud=mode == 'hana-cloud',
        )

        out = self.config.output_dir / 'pom.xml'
        out.write_text(content, encoding='utf-8')
