"""
Light wrapper around javalang for extracting structural info.
Falls back gracefully if javalang can't parse the file.
"""
import re
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import javalang
    _JAVALANG_AVAILABLE = True
except ImportError:
    _JAVALANG_AVAILABLE = False

IMPORT_PATTERN = re.compile(r'^\s*import\s+(static\s+)?([\w.]+(?:\.\*)?)\s*;', re.MULTILINE)
CLASS_PATTERN = re.compile(r'\b(?:public\s+)?(?:abstract\s+)?(?:class|interface|enum)\s+(\w+)')
PACKAGE_PATTERN = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)


def parse_file(source: str) -> Dict[str, Any]:
    result = {
        'package': None,
        'imports': [],
        'class_name': None,
        'parsed': False,
    }

    # Always extract via regex as fallback
    pkg = PACKAGE_PATTERN.search(source)
    result['package'] = pkg.group(1) if pkg else None
    result['imports'] = [m.group(2) for m in IMPORT_PATTERN.finditer(source)]
    cls = CLASS_PATTERN.search(source)
    result['class_name'] = cls.group(1) if cls else None

    if not _JAVALANG_AVAILABLE:
        return result

    try:
        tree = javalang.parse.parse(source)
        if tree.package:
            result['package'] = tree.package.name
        result['imports'] = [i.path for i in (tree.imports or [])]
        if tree.types:
            result['class_name'] = tree.types[0].name
        result['parsed'] = True
    except Exception:
        pass  # regex result is sufficient

    return result
