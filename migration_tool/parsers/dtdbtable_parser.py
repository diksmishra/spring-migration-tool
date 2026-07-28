"""
Parser for SAP NWDS ABAP Dictionary (.dtdbtable) files.

Format: XMI/XML wrapping a <dictionary:DBTable> element.
Supports individual file parsing and bulk extraction from a ZIP archive.
"""
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

# XML namespaces used in NWDS DDIC files
_DICT_NS = 'com.sap.ide.dictionary.model.dictionary'
_XMI_NS  = 'http://www.omg.org/XMI'

# NWDS builtInType → HANA Cloud SQL type
_TYPE_MAP = {
    'string':    lambda length: f'NVARCHAR({length})' if length else 'NVARCHAR(5000)',
    'long':      lambda _:      'BIGINT',
    'int':       lambda _:      'INTEGER',
    'timestamp': lambda _:      'TIMESTAMP',
    'date':      lambda _:      'DATE',
    'float':     lambda _:      'FLOAT',
    'double':    lambda _:      'DOUBLE',
    'decimal':   lambda _:      'DECIMAL',
    'binary':    lambda length: f'VARBINARY({length})' if length else 'VARBINARY(5000)',
    'boolean':   lambda _:      'BOOLEAN',
}


def _to_hana_type(built_in_type: str, length: str) -> str:
    fn = _TYPE_MAP.get(built_in_type.lower())
    return fn(length) if fn else 'NVARCHAR(100)'


def parse_dtdbtable_content(xml_content: str) -> Optional[Dict]:
    """Parse a single .dtdbtable XMI string into a table definition dict.

    Returns:
        {
            'table_name': str,
            'columns': [
                {'name': str, 'sql_type': str, 'key_flag': bool,
                 'not_null': bool, 'description': str},
                ...
            ]
        }
        or None if the file cannot be parsed.
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return None

    # <dictionary:DBTable> — try with and without namespace
    table_elem = root.find(f'{{{_DICT_NS}}}DBTable')
    if table_elem is None:
        table_elem = root.find('DBTable')
    if table_elem is None:
        return None

    table_name = table_elem.get('name', '').strip()
    if not table_name:
        return None

    columns: List[Dict] = []
    for col in table_elem.findall('columns'):
        col_name = col.get('name', '').strip()
        if not col_name:
            continue

        key_flag    = col.get('keyFlag',     'false').lower() == 'true'
        not_null    = col.get('notNullFlag', 'false').lower() == 'true'
        description = col.get('description', '')

        simple = col.find('simpleType')
        if simple is not None:
            built_in = simple.get('builtInType', 'string')
            length   = simple.get('length', '')
            sql_type = _to_hana_type(built_in, length)
        else:
            sql_type = 'NVARCHAR(100)'

        columns.append({
            'name':        col_name,
            'sql_type':    sql_type,
            'key_flag':    key_flag,
            'not_null':    not_null or key_flag,  # PK columns must be NOT NULL
            'description': description,
        })

    return {'table_name': table_name, 'columns': columns}


def parse_zip(zip_path: str) -> List[Dict]:
    """Extract and parse all .dtdbtable files from a ZIP archive.

    Ignores .xlf companion files and any entries that fail to parse.
    """
    path = Path(zip_path)
    if not path.is_file():
        raise FileNotFoundError(f'ZIP file not found: {zip_path}')

    tables: List[Dict] = []
    with zipfile.ZipFile(path, 'r') as zf:
        for entry in zf.namelist():
            # Match *.dtdbtable regardless of path depth; skip .xlf companions
            if Path(entry).suffix.lower() == '.dtdbtable':
                try:
                    content = zf.read(entry).decode('utf-8', errors='replace')
                    table = parse_dtdbtable_content(content)
                    if table:
                        tables.append(table)
                except Exception:
                    continue  # skip corrupt or unreadable entries

    return tables
