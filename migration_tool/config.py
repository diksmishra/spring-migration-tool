from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List


@dataclass
class MigrationConfig:
    source_dir: Path
    output_dir: Path
    base_package: str
    group_id: str
    artifact_id: str
    spring_boot_version: str
    java_version: str
    persistence_mode: str          # 'jpa' | 'jdbc' | 'sap' | 'hana-cloud'
    hdi_service_name: str = ''     # BTP CF service instance name (hana-cloud mode only)
    db_artifacts_zip: str = ''     # Path to ZIP with .dtdbtable files (hana-cloud mode only)
    unavailable_packages: List[str] = field(default_factory=list)  # extra import prefixes to flag+comment out
    scan_result: Dict[str, Any] = field(default_factory=dict)

    @property
    def main_class_name(self) -> str:
        parts = self.artifact_id.replace('-', ' ').replace('_', ' ').title().replace(' ', '')
        return f"{parts}Application"

    @property
    def package_path(self) -> str:
        return self.base_package.replace('.', '/')

    @property
    def src_main_java(self) -> Path:
        return self.output_dir / 'src' / 'main' / 'java'

    @property
    def src_main_resources(self) -> Path:
        return self.output_dir / 'src' / 'main' / 'resources'
