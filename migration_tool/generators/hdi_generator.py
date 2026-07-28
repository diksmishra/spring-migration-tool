"""
Generator for HANA Cloud HDI artifacts.

Reads .dtdbtable files from a ZIP archive and produces:
  db/src/<TABLE_NAME>.hdbtable   — one per table
  db/src/.hdiconfig              — HDI plugin declarations
  db/src/.hdinamespace           — empty namespace (no prefix)
  db/package.json                — @sap/hdi-deploy entry point
"""
import json
from pathlib import Path
from typing import Dict, List

from migration_tool.config import MigrationConfig
from migration_tool.parsers.dtdbtable_parser import parse_zip

_HDICONFIG = {
    'file_suffixes': {
        'hdbtable':    {'plugin_name': 'com.sap.hana.di.table'},
        'hdbsequence': {'plugin_name': 'com.sap.hana.di.sequence'},
        'hdbview':     {'plugin_name': 'com.sap.hana.di.view'},
        'hdbindex':    {'plugin_name': 'com.sap.hana.di.index'},
    }
}

_HDINAMESPACE = {'name': '', 'subfolder': 'ignore'}


def _infer_pk(columns: List[Dict]) -> List[Dict]:
    """Return key columns; if none are flagged, pick a heuristic candidate.

    HANA Cloud enforces that all column store tables must have a primary key.
    """
    pk_cols = [c for c in columns if c['key_flag']]
    if pk_cols:
        return pk_cols

    # Heuristic: prefer well-known ID column names
    for c in columns:
        if c['name'].upper() in ('ROW_ID', 'ID'):
            c['key_flag'] = True
            c['not_null'] = True
            return [c]
    for c in columns:
        upper = c['name'].upper()
        if upper.endswith('_ID') or upper.endswith('_NAME') or upper.endswith('_NO'):
            c['key_flag'] = True
            c['not_null'] = True
            return [c]

    # Last resort: promote the first column
    columns[0]['key_flag'] = True
    columns[0]['not_null'] = True
    return [columns[0]]


def _render_hdbtable(table: Dict) -> str:
    """Render a single .hdbtable file from a parsed table definition."""
    columns  = [dict(c) for c in table['columns']]  # shallow copy to avoid mutation
    had_no_pk = not any(c['key_flag'] for c in columns)
    pk_cols  = _infer_pk(columns)

    lines = []
    if had_no_pk:
        pk_names = ', '.join(f'"{c["name"]}"' for c in pk_cols)
        lines.append(
            f'-- NOTE: No primary key in source DDIC. '
            f'{pk_names} selected heuristically — verify before production deploy.'
        )

    lines.append(f'COLUMN TABLE "{table["table_name"]}" (')

    col_defs = []
    for c in columns:
        nn = ' NOT NULL' if c['not_null'] else ''
        col_defs.append(f'    "{c["name"]}" {c["sql_type"]}{nn}')

    pk_clause = ', '.join(f'"{c["name"]}"' for c in pk_cols)
    col_defs.append(f'    PRIMARY KEY ({pk_clause})')

    lines.append(',\n'.join(col_defs))
    lines.append(');')
    return '\n'.join(lines) + '\n'


class HdiGenerator:
    def __init__(self, config: MigrationConfig):
        self.config = config

    def generate(self) -> int:
        """Generate HDI artifacts from the configured ZIP.

        Returns the number of tables generated, or 0 if skipped.
        """
        if self.config.persistence_mode != 'hana-cloud':
            return 0
        if not self.config.db_artifacts_zip:
            return 0

        try:
            tables = parse_zip(self.config.db_artifacts_zip)
        except Exception as exc:
            from rich.console import Console
            Console().print(f'[yellow]⚠  Could not parse DB artifacts ZIP: {exc}[/yellow]')
            return 0

        if not tables:
            return 0

        db_src = self.config.output_dir / 'db' / 'src'
        db_src.mkdir(parents=True, exist_ok=True)

        # .hdiconfig and .hdinamespace must be inside src/ so the deployer uploads them
        (db_src / '.hdiconfig').write_text(
            json.dumps(_HDICONFIG, indent=2) + '\n', encoding='utf-8'
        )
        (db_src / '.hdinamespace').write_text(
            json.dumps(_HDINAMESPACE, indent=2) + '\n', encoding='utf-8'
        )

        for table in tables:
            content = _render_hdbtable(table)
            (db_src / f'{table["table_name"]}.hdbtable').write_text(content, encoding='utf-8')

        # db/package.json — entry point for @sap/hdi-deploy on BTP CF
        pkg = {
            'name':         f'{self.config.artifact_id}-db',
            'version':      '1.0.0',
            'description':  'HANA Cloud HDI table artifacts',
            'scripts':      {'start': 'node node_modules/@sap/hdi-deploy/deploy.js'},
            'dependencies': {'@sap/hdi-deploy': '^4.8.0'},
            'engines':      {'node': '>=18'},
        }
        (self.config.output_dir / 'db' / 'package.json').write_text(
            json.dumps(pkg, indent=2) + '\n', encoding='utf-8'
        )

        return len(tables)
