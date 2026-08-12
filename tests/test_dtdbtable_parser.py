"""Tests for dtdbtable_parser — verifies parsing against the real MetaDataAPI
export schema (root <DtDbTable>, <DtField> columns, separate PrimaryKey section),
not a hypothetical XMI/<dictionary:DBTable> schema no real export uses."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import zipfile
from migration_tool.parsers.dtdbtable_parser import parse_dtdbtable_content, parse_zip

NS = 'http://xml.sap.com/2002/10/metamodel/dictionary'


def _table_xml(name, fields_xml, key_names=()):
    key_refs = ''.join(f'<Core.Reference path="StructureElement:{k}"/>' for k in key_names)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<DtDbTable xmlns="{NS}" name="{name}" package="" masterLanguage="en">
    <DtStructure.StructureElements>
        {fields_xml}
    </DtStructure.StructureElements>
    <DtDbTable.PrimaryKey>
        <DtPrimaryKey name="PrimaryKey">
            <DtPrimaryKey.KeyElements>
                {key_refs}
            </DtPrimaryKey.KeyElements>
        </DtPrimaryKey>
    </DtDbTable.PrimaryKey>
</DtDbTable>'''


def test_parses_table_name():
    xml = _table_xml('ZAP_RES_DATA', '<DtField builtInType="string" name="VENDOR_NO" length="10" notNull="false"/>')
    table = parse_dtdbtable_content(xml)
    assert table['table_name'] == 'ZAP_RES_DATA'


def test_parses_column_with_length_and_type():
    xml = _table_xml('T1', '<DtField builtInType="string" name="VENDOR_NAME" length="80" notNull="false"/>')
    table = parse_dtdbtable_content(xml)
    col = table['columns'][0]
    assert col['name'] == 'VENDOR_NAME'
    assert col['sql_type'] == 'NVARCHAR(80)'
    assert col['not_null'] is False


def test_primary_key_referenced_separately_not_a_column_attribute():
    xml = _table_xml(
        'ZAP_RES_ASSC',
        '<DtField builtInType="long" name="REQUEST_ID" notNull="true"/>'
        '<DtField builtInType="long" name="ASSC_ID" notNull="true"/>'
        '<DtField builtInType="string" name="NOTES" length="500" notNull="false"/>',
        key_names=('REQUEST_ID', 'ASSC_ID'),
    )
    table = parse_dtdbtable_content(xml)
    by_name = {c['name']: c for c in table['columns']}
    assert by_name['REQUEST_ID']['key_flag'] is True
    assert by_name['ASSC_ID']['key_flag'] is True
    assert by_name['NOTES']['key_flag'] is False
    # PK columns must be NOT NULL regardless of the source notNull value
    assert by_name['REQUEST_ID']['not_null'] is True


def test_table_with_no_primary_key_elements_leaves_all_columns_unflagged():
    """No KeyElements means HdiGenerator's own heuristic PK assignment must take over."""
    xml = _table_xml('ZAP_RESEARCH_AUDIT', '<DtField builtInType="string" name="DDDUMMY" notNull="false"/>')
    table = parse_dtdbtable_content(xml)
    assert all(not c['key_flag'] for c in table['columns'])


def test_returns_none_for_wrong_root_element():
    xml = f'<?xml version="1.0"?><SomethingElse xmlns="{NS}" name="X"/>'
    assert parse_dtdbtable_content(xml) is None


def test_returns_none_for_malformed_xml():
    assert parse_dtdbtable_content('<not valid xml') is None


def test_returns_none_for_missing_table_name():
    xml = f'<DtDbTable xmlns="{NS}"><DtStructure.StructureElements/></DtDbTable>'
    assert parse_dtdbtable_content(xml) is None


def test_parse_zip_ignores_xlf_and_non_dtdbtable_entries(tmp_path):
    zip_path = tmp_path / 'db.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('db/T1.dtdbtable', _table_xml('T1', '<DtField builtInType="int" name="ID" notNull="true"/>'))
        zf.writestr('db/T1.dtdbtable.xlf', '<not a table, just a translation file/>')
        zf.writestr('db/SOME_IDX.dtdbindex', '<irrelevant/>')

    tables = parse_zip(str(zip_path))
    assert len(tables) == 1
    assert tables[0]['table_name'] == 'T1'


def test_parse_zip_skips_corrupt_entries_without_raising(tmp_path):
    zip_path = tmp_path / 'db.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('db/GOOD.dtdbtable', _table_xml('GOOD', '<DtField builtInType="int" name="ID" notNull="true"/>'))
        zf.writestr('db/BAD.dtdbtable', '<not valid xml')

    tables = parse_zip(str(zip_path))
    assert len(tables) == 1
    assert tables[0]['table_name'] == 'GOOD'
