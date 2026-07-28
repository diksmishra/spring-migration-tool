from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from migration_tool.config import MigrationConfig


class AppClassGenerator:
    def __init__(self, config: MigrationConfig):
        self.config = config

    def generate(self):
        env = Environment(
            loader=FileSystemLoader(
                Path(__file__).parent.parent.parent / 'templates'
            )
        )
        template = env.get_template('Application.java.j2')
        content = template.render(
            base_package=self.config.base_package,
            class_name=self.config.main_class_name,
        )

        out_dir = self.config.src_main_java / self.config.package_path
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f'{self.config.main_class_name}.java'
        out.write_text(content, encoding='utf-8')
