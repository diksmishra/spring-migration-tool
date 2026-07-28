import re
from pathlib import Path
from typing import Dict, Any, List


# Patterns that identify file type by class-level annotations or naming
CONTROLLER_PATTERNS = [
    re.compile(r'@RestController'),
    re.compile(r'@Controller'),
]
SERVICE_PATTERNS = [
    re.compile(r'@Service'),
]
REPOSITORY_PATTERNS = [
    re.compile(r'@Repository'),
    re.compile(r'extends\s+\w*(Repository|Dao|DAO)\w*'),
    re.compile(r'implements\s+\w*(Repository|Dao|DAO)\w*'),
    re.compile(r'class\s+\w*(Repository|Dao|DAO)\w*'),
]
MODEL_PATTERNS = [
    re.compile(r'@Entity'),
    re.compile(r'class\s+\w+(DO|SDO|DTO|Entity)\b'),
]
SAP_LOGGING_PATTERN = re.compile(r'import\s+com\.sap\.tc\.logging\.')
JAVAX_PERSISTENCE_PATTERN = re.compile(r'import\s+javax\.persistence\.')
JNDI_PATTERN = re.compile(r'InitialContext|Context\.lookup|javax\.naming\.')
SAP_SECURITY_PATTERN = re.compile(r'import\s+com\.sap\.security\.')
SAP_JCO_PATTERN = re.compile(r'import\s+com\.sap\.conn\.jco\.|import\s+com\.sap\.mw\.jco\.')
PACKAGE_PATTERN = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)


class ProjectScanner:
    def __init__(self, source_dir: Path):
        self.source_dir = source_dir

    def scan(self) -> Dict[str, Any]:
        all_java_files = list(self.source_dir.rglob('*.java'))

        counts = {
            'controllers': 0, 'services': 0, 'models': 0,
            'daos': 0, 'other': 0,
            'sap_logging_files': 0, 'javax_persistence_files': 0,
            'jndi_files': 0, 'sap_security_files': 0, 'sap_jco_files': 0,
        }
        classified = {'controllers': [], 'services': [], 'models': [], 'daos': [], 'other': []}
        packages = []
        todo_patterns = {
            'jndi': [], 'sap_security': [], 'sap_jco': []
        }

        for java_file in all_java_files:
            try:
                source = java_file.read_text(encoding='utf-8', errors='replace')
            except Exception:
                continue

            # Detect base package
            pkg_match = PACKAGE_PATTERN.search(source)
            if pkg_match:
                packages.append(pkg_match.group(1))

            # Count special patterns
            if SAP_LOGGING_PATTERN.search(source):
                counts['sap_logging_files'] += 1
            if JAVAX_PERSISTENCE_PATTERN.search(source):
                counts['javax_persistence_files'] += 1
            if JNDI_PATTERN.search(source):
                counts['jndi_files'] += 1
                todo_patterns['jndi'].append(str(java_file))
            if SAP_SECURITY_PATTERN.search(source):
                counts['sap_security_files'] += 1
                todo_patterns['sap_security'].append(str(java_file))
            if SAP_JCO_PATTERN.search(source):
                counts['sap_jco_files'] += 1
                todo_patterns['sap_jco'].append(str(java_file))

            # Classify
            category = self._classify(source, java_file.name)
            counts[category] += 1
            classified[category].append(java_file)

        return {
            'all_java_files': all_java_files,
            'classified': classified,
            'counts': counts,
            'todo_patterns': todo_patterns,
            'detected_base_package': self._detect_base_package(packages),
        }

    def _classify(self, source: str, filename: str) -> str:
        if any(p.search(source) for p in CONTROLLER_PATTERNS):
            return 'controllers'
        if any(p.search(source) for p in SERVICE_PATTERNS):
            return 'services'
        if any(p.search(source) for p in REPOSITORY_PATTERNS):
            return 'daos'
        if any(p.search(source) for p in MODEL_PATTERNS):
            return 'models'
        # Fallback: filename-based heuristics
        name_lower = filename.lower()
        if 'controller' in name_lower:
            return 'controllers'
        if 'service' in name_lower:
            return 'services'
        if 'repo' in name_lower or 'dao' in name_lower:
            return 'daos'
        if name_lower.endswith(('do.java', 'sdo.java', 'dto.java')):
            return 'models'
        return 'other'

    # Package segments that are never the root — strip them from the detected base
    _LEAF_SEGMENTS = {
        'controller', 'controllers', 'service', 'services', 'impl',
        'model', 'models', 'dao', 'daos', 'repository', 'repositories',
        'entity', 'entities', 'dto', 'qo', 'config', 'configuration',
        'exception', 'exceptions', 'util', 'utils', 'helper', 'helpers',
        'screen', 'domain', 'web', 'rest', 'api',
    }

    def _detect_base_package(self, packages: List[str]) -> str:
        if not packages:
            return ''
        # Find the common prefix among all packages
        split = [p.split('.') for p in packages]
        common = split[0]
        for parts in split[1:]:
            common = [c for c, p in zip(common, parts) if c == p]
            if not common:
                break
        # Strip trailing segments that are well-known sub-package names
        while common and common[-1].lower() in self._LEAF_SEGMENTS:
            common = common[:-1]
        return '.'.join(common) if common else packages[0]
