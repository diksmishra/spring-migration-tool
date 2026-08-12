"""
Parser for SAP NWDS ABAP Dictionary (.dtdbtable) files.

Format: MetaDataAPI-generated XML. The root element IS the table
(<DtDbTable name="..." xmlns="http://xml.sap.com/2002/10/metamodel/dictionary">),
with columns as <DtField> elements under <DtStructure.StructureElements>, and
primary key columns declared separately under <DtDbTable.PrimaryKey> via
<Core.Reference path="StructureElement:COL_NAME"/> — key membership is not a
per-column attribute.
Supports individual file parsing and bulk extraction from a ZIP archive.
"""
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

# Default namespace declared on the <DtDbTable> root in real MetaDataAPI exports
_NWDS_NS = 'http://xml.sap.com/2002/10/metamodel/dictionary'


def _q(tag: str) -> str:
    return f'{{{_NWDS_NS}}}{tag}'

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
    """Parse a single .dtdbtable XML string into a table definition dict.

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

    # The root element is the table itself, not a nested child.
    if root.tag != _q('DtDbTable'):
        return None

    table_name = root.get('name', '').strip()
    if not table_name:
        return None

    # Primary key columns are declared separately, referenced by name —
    # not a per-column attribute like keyFlag.
    key_names = set()
    for ref in root.iter(_q('Core.Reference')):
        path = ref.get('path', '')
        if path.startswith('StructureElement:'):
            key_names.add(path.split(':', 1)[1])

    columns: List[Dict] = []
    struct_elements = root.find(_q('DtStructure.StructureElements'))
    if struct_elements is not None:
        for field in struct_elements.findall(_q('DtField')):
            col_name = field.get('name', '').strip()
            if not col_name:
                continue

            built_in = field.get('builtInType', 'string')
            length   = field.get('length', '')
            sql_type = _to_hana_type(built_in, length)

            key_flag = col_name in key_names
            not_null = field.get('notNull', 'false').lower() == 'true'

            columns.append({
                'name':        col_name,
                'sql_type':    sql_type,
                'key_flag':    key_flag,
                'not_null':    not_null or key_flag,  # PK columns must be NOT NULL
                'description': '',
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
