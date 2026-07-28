from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from migration_tool.config import MigrationConfig


class PropertiesGenerator:
    def __init__(self, config: MigrationConfig):
        self.config = config

    def generate(self):
        env = Environment(
            loader=FileSystemLoader(
                Path(__file__).parent.parent.parent / 'templates'
            )
        )
        mode = self.config.persistence_mode
        scan = self.config.scan_result

        # application.properties — profile-agnostic common settings
        content = env.get_template('application.properties.j2').render(
            artifact_id=self.config.artifact_id,
            base_package=self.config.base_package,
            persistence_mode=mode,
            has_jndi=bool(scan.get('counts', {}).get('jndi_files', 0)),
            has_jpa=mode == 'jpa',
            has_jdbc=mode == 'jdbc',
            has_hana_cloud=mode == 'hana-cloud',
            hdi_service_name=self.config.hdi_service_name,
        )
        res_dir = self.config.src_main_resources
        res_dir.mkdir(parents=True, exist_ok=True)
        (res_dir / 'application.properties').write_text(content, encoding='utf-8')

        if mode != 'hana-cloud':
            return

        # application-cloud.properties — BTP CF datasource via vcap.services.*
        cloud_content = env.get_template('application-cloud.properties.j2').render(
            artifact_id=self.config.artifact_id,
            hdi_service_name=self.config.hdi_service_name or f'{self.config.artifact_id}-hdi',
        )
        (res_dir / 'application-cloud.properties').write_text(cloud_content, encoding='utf-8')

        # application-local.properties — template for local dev credentials
        local_props = (
            '# ── Local development profile ────────────────────────────────────────────────\n'
            '# Activate with: mvn spring-boot:run -Dspring-boot.run.profiles=local\n'
            '# Use a personal dev HANA Cloud instance — never shared or production credentials.\n'
            '#\n'
            '# HDI JDBC URL format:\n'
            '#   jdbc:sap://<host>:443?encrypt=true&currentschema=<SCHEMA_NAME>\n'
            '#\n'
            'spring.datasource.url=jdbc:sap://YOUR_HANA_HOST.hanacloud.ondemand.com:443'
            '?encrypt=true&currentschema=YOUR_SCHEMA_NAME\n'
            'spring.datasource.username=YOUR_HDI_USER\n'
            'spring.datasource.password=YOUR_HDI_PASSWORD\n'
            'spring.datasource.driver-class-name=com.sap.db.jdbc.Driver\n'
        )
        (res_dir / 'application-local.properties').write_text(local_props, encoding='utf-8')
