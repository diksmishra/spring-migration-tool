import re
from pathlib import Path
from typing import Dict, Any, List


# ── Class-level classification patterns ───────────────────────────────────────

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
ENUM_PATTERN    = re.compile(r'\benum\s+\w+')
TEST_PATTERNS   = [
    re.compile(r'import\s+org\.junit\.'),
    re.compile(r'import\s+org\.junit\.jupiter\.'),
    re.compile(r'@SpringBootTest'),
    re.compile(r'@WebMvcTest'),
    re.compile(r'@DataJpaTest'),
    re.compile(r'@RunWith\s*\('),
    re.compile(r'@ExtendWith\s*\('),
]

# ── Special-pattern detectors ─────────────────────────────────────────────────

SAP_LOGGING_PATTERN   = re.compile(r'import\s+com\.sap\.tc\.logging\.')
JAVAX_PERSISTENCE_PATTERN = re.compile(r'import\s+javax\.persistence\.')
JNDI_PATTERN          = re.compile(r'InitialContext|Context\.lookup|javax\.naming\.')
SAP_SECURITY_PATTERN  = re.compile(r'import\s+com\.sap\.security\.')
SAP_JCO_PATTERN       = re.compile(r'import\s+com\.sap\.conn\.jco\.|import\s+com\.sap\.mw\.jco\.')
SAP_ENGINE_PATTERN    = re.compile(r'import\s+com\.sap\.engine\.')
PACKAGE_PATTERN       = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)

# Packages that belong to a nascent Spring Boot scaffold, not the legacy app.
# Files whose package matches any of these are skipped entirely.
SCAFFOLD_PACKAGE_FRAGMENTS = ['shreya']


class ProjectScanner:
    def __init__(self, source_dir: Path):
        self.source_dir = source_dir

    def scan(self) -> Dict[str, Any]:
        all_java_files = list(self.source_dir.rglob('*.java'))

        counts = {
            'controllers': 0, 'services': 0, 'models': 0,
            'daos': 0, 'enums': 0, 'utils': 0, 'tests': 0,
            'other': 0, 'skipped_scaffold': 0,
            'sap_logging_files': 0, 'javax_persistence_files': 0,
            'jndi_files': 0, 'sap_security_files': 0,
            'sap_jco_files': 0, 'sap_engine_files': 0,
        }
        classified = {
            'controllers': [], 'services': [], 'models': [],
            'daos': [], 'enums': [], 'utils': [], 'tests': [],
            'other': [], 'skipped': [],
        }
        packages = []
        todo_patterns = {'jndi': [], 'sap_security': [], 'sap_jco': [], 'sap_engine': []}

        for java_file in all_java_files:
            try:
                source = java_file.read_text(encoding='utf-8', errors='replace')
            except Exception:
                continue

            # Detect package
            pkg_match = PACKAGE_PATTERN.search(source)
            pkg = pkg_match.group(1) if pkg_match else ''

            # Skip scaffold files (wrong base package — not legacy code)
            if any(frag in pkg for frag in SCAFFOLD_PACKAGE_FRAGMENTS):
                counts['skipped_scaffold'] += 1
                classified['skipped'].append(java_file)
                continue

            if pkg:
                packages.append(pkg)

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
            if SAP_ENGINE_PATTERN.search(source):
                counts['sap_engine_files'] += 1
                todo_patterns['sap_engine'].append(str(java_file))

            # Classify
            category = self._classify(source, java_file, pkg)
            counts[category] += 1
            classified[category].append(java_file)

        return {
            'all_java_files': all_java_files,
            'classified': classified,
            'counts': counts,
            'todo_patterns': todo_patterns,
            'detected_base_package': self._detect_base_package(packages),
        }

    def _classify(self, source: str, java_file: Path, pkg: str) -> str:
        # Test files — check path and imports before class-level patterns
        path_str = str(java_file).replace('\\', '/')
        if '/test/' in path_str or any(p.search(source) for p in TEST_PATTERNS):
            return 'tests'
        if java_file.name.endswith(('Test.java', 'Tests.java', 'IT.java')):
            return 'tests'

        # Enum
        if ENUM_PATTERN.search(source):
            return 'enums'

        # Standard class-level annotations
        if any(p.search(source) for p in CONTROLLER_PATTERNS):
            return 'controllers'
        if any(p.search(source) for p in SERVICE_PATTERNS):
            return 'services'
        if any(p.search(source) for p in REPOSITORY_PATTERNS):
            return 'daos'
        if any(p.search(source) for p in MODEL_PATTERNS):
            return 'models'

        # Filename-based heuristics
        name_lower = java_file.name.lower()
        if 'controller' in name_lower:
            return 'controllers'
        if 'service' in name_lower:
            return 'services'
        if 'repo' in name_lower or 'dao' in name_lower:
            return 'daos'
        if name_lower.endswith(('do.java', 'sdo.java', 'dto.java', 'qo.java')):
            return 'models'

        # Package-based heuristics
        pkg_lower = pkg.lower()
        if pkg_lower.endswith('.utils') or pkg_lower.endswith('.util'):
            return 'utils'
        if pkg_lower.endswith('.co') or pkg_lower.endswith('.constants'):
            return 'enums'
        if 'util' in name_lower or 'helper' in name_lower or 'handler' in name_lower:
            return 'utils'

        return 'other'

    # Package segments that are never the root — strip them from the detected base
    _LEAF_SEGMENTS = {
        'controller', 'controllers', 'service', 'services', 'impl',
        'model', 'models', 'dao', 'daos', 'repository', 'repositories',
        'entity', 'entities', 'dto', 'qo', 'co', 'config', 'configuration',
        'exception', 'exceptions', 'util', 'utils', 'helper', 'helpers',
        'screen', 'domain', 'web', 'rest', 'api', 'test', 'tests',
    }

    def _detect_base_package(self, packages: List[str]) -> str:
        if not packages:
            return ''
        split  = [p.split('.') for p in packages]
        common = split[0]
        for parts in split[1:]:
            common = [c for c, p in zip(common, parts) if c == p]
            if not common:
                break
        while common and common[-1].lower() in self._LEAF_SEGMENTS:
            common = common[:-1]
        return '.'.join(common) if common else packages[0]
