import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from migration_tool.config import MigrationConfig


class ManifestGenerator:
    def __init__(self, config: MigrationConfig):
        self.config = config

    def generate(self):
        if self.config.persistence_mode != 'hana-cloud':
            return

        env = Environment(
            loader=FileSystemLoader(
                Path(__file__).parent.parent.parent / 'templates'
            )
        )

        svc = self.config.hdi_service_name or f'{self.config.artifact_id}-hdi'

        # manifest.yml — standalone CF push (single-module, no HDI deployer)
        manifest_content = env.get_template('manifest.yml.j2').render(
            artifact_id=self.config.artifact_id,
            java_version=self.config.java_version,
            hdi_service_name=svc,
        )
        (self.config.output_dir / 'manifest.yml').write_text(manifest_content, encoding='utf-8')

        # mta.yaml — full MTA deploy (HDI deployer + Java app as separate modules)
        has_db = bool(self.config.db_artifacts_zip)
        mta_content = env.get_template('mta.yaml.j2').render(
            artifact_id=self.config.artifact_id,
            java_version=self.config.java_version,
            hdi_service_name=svc,
            has_db_module=has_db,
        )
        (self.config.output_dir / 'mta.yaml').write_text(mta_content, encoding='utf-8')

        # package.json — root-level npm deploy script
        mtar = f'{self.config.artifact_id}_1.0.0.mtar'
        pkg = {
            'name': self.config.artifact_id,
            'private': True,
            'scripts': {
                'deploy': f'mvn clean package -DskipTests && mbt build && cf deploy mta_archives/{mtar}'
            }
        }
        (self.config.output_dir / 'package.json').write_text(
            json.dumps(pkg, indent=2) + '\n', encoding='utf-8'
        )
