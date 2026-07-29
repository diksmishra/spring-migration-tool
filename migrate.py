#!/usr/bin/env python3
"""
SAP NetWeaver -> Spring Boot Migration Tool
Usage: python migrate.py SOURCE_DIR [--output OUTPUT_DIR] [--non-interactive]
"""
import re
from pathlib import Path
import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TaskProgressColumn
from rich.table import Table

from migration_tool.config import MigrationConfig
from migration_tool.analyzer.scanner import ProjectScanner
from migration_tool.transformers.logging_transformer import LoggingTransformer
from migration_tool.transformers.import_transformer import ImportTransformer
from migration_tool.transformers.persistence_transformer import PersistenceTransformer
from migration_tool.transformers.utils_transformer import UtilsTransformer
from migration_tool.generators.pom_generator import PomGenerator
from migration_tool.generators.app_class_generator import AppClassGenerator
from migration_tool.generators.properties_generator import PropertiesGenerator
from migration_tool.generators.manifest_generator import ManifestGenerator
from migration_tool.generators.hdi_generator import HdiGenerator
from migration_tool.reporter import Reporter

console = Console()


@click.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output',            '-o', default=None, help='Output directory for converted project')
@click.option('--group-id',          '-g', default=None, help='Maven group ID (e.g. com.truist.fsr)')
@click.option('--artifact-id',       '-a', default=None, help='Maven artifact ID (e.g. fsr-regrep)')
@click.option('--persistence',       '-p',
              type=click.Choice(['jpa', 'jdbc', 'sap', 'hana-cloud'], case_sensitive=False),
              default=None,
              help='Persistence layer: jpa (default), jdbc, sap (flag only), hana-cloud (BTP CF)')
@click.option('--spring-boot-version', default=None, help='Spring Boot version (default: 3.2.5)')
@click.option('--java-version',        default=None, help='Java version (default: 17)')
@click.option('--db-artifacts',      '-d', default=None,
              help='Path to ZIP with .dtdbtable files — generates HDI artifacts (hana-cloud only)')
@click.option('--non-interactive', is_flag=True, default=False,
              help='Skip prompts and use defaults / provided options')
def main(source_dir, output, group_id, artifact_id, persistence,
         spring_boot_version, java_version, db_artifacts, non_interactive):

    source_path = Path(source_dir).resolve()

    console.print()
    console.print(Panel.fit(
        '[bold blue]SAP NetWeaver -> Spring Boot Migration Tool[/bold blue]',
        border_style='blue'
    ))
    console.print()

    # ── Scan ──────────────────────────────────────────────────────────────────
    console.print(f'[dim]Scanning project:[/dim] [bold]{source_path}[/bold]')
    scanner    = ProjectScanner(source_path)
    scan_result = scanner.scan()

    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column(style='green')
    tbl.add_column(style='bold white')
    tbl.add_row('Controllers',        str(scan_result['counts']['controllers']))
    tbl.add_row('Services',           str(scan_result['counts']['services']))
    tbl.add_row('Models/DTOs',        str(scan_result['counts']['models']))
    tbl.add_row('DAOs/Repos',         str(scan_result['counts']['daos']))
    tbl.add_row('Enums (co/)',        str(scan_result['counts']['enums']))
    tbl.add_row('Utils',              str(scan_result['counts']['utils']))
    tbl.add_row('Tests',              str(scan_result['counts']['tests']))
    tbl.add_row('Other classes',      str(scan_result['counts']['other']))
    if scan_result['counts']['skipped_scaffold']:
        tbl.add_row('[yellow]Skipped (scaffold)[/yellow]',
                    str(scan_result['counts']['skipped_scaffold']))
    tbl.add_row('SAP logging found in', f"{scan_result['counts']['sap_logging_files']} files")
    if scan_result['counts']['sap_engine_files']:
        tbl.add_row('[yellow]SAP platform API in[/yellow]',
                    f"{scan_result['counts']['sap_engine_files']} files (manual rewrite needed)")
    if scan_result['counts']['javax_persistence_files']:
        tbl.add_row(
            'javax.persistence found in',
            f"{scan_result['counts']['javax_persistence_files']} files (will become jakarta.*)"
        )
    console.print(tbl)
    console.print()

    # ── Collect configuration ─────────────────────────────────────────────────
    detected_package = scan_result.get('detected_base_package', '')

    if non_interactive:
        final_group_id        = group_id or (detected_package.rsplit('.', 1)[0] if detected_package else 'com.example')
        final_artifact_id     = artifact_id or source_path.name.lower().replace(' ', '-').replace('_', '-')
        final_package         = detected_package or 'com.example.app'
        final_persistence     = persistence or 'jpa'
        final_sb_version      = spring_boot_version or '3.2.5'
        final_java_version    = java_version or '17'
        final_hdi_service     = ''
        final_db_artifacts    = db_artifacts or ''
    else:
        console.print('[bold]Configure your migration:[/bold]')
        console.print()

        default_package  = detected_package or 'com.example.app'
        final_package    = Prompt.ask('  [cyan][1/5][/cyan] Base package', default=default_package)

        default_group    = group_id or (final_package.rsplit('.', 1)[0] if '.' in final_package else final_package)
        final_group_id   = Prompt.ask('  [cyan][2/5][/cyan] Group ID', default=default_group)

        default_artifact = artifact_id or source_path.name.lower().replace(' ', '-').replace('_', '-')
        final_artifact_id = Prompt.ask('  [cyan][3/5][/cyan] Artifact ID', default=default_artifact)

        final_sb_version   = Prompt.ask('  [cyan][4/5][/cyan] Spring Boot version', default=spring_boot_version or '3.2.5')
        final_java_version = Prompt.ask('  [cyan][4b/5][/cyan] Java version',        default=java_version or '17')

        console.print()
        console.print('  [cyan][5/5][/cyan] Persistence layer:')
        console.print('         [bold](1)[/bold] Standard JPA -- @Entity, EntityManager  [dim][DEFAULT][/dim]')
        console.print('         [bold](2)[/bold] JDBC -- JdbcTemplate, JNDI DataSource')
        console.print('         [bold](3)[/bold] SAP-proprietary -- flag all DAO classes for manual migration')
        console.print('         [bold](4)[/bold] HANA Cloud (BTP CF) -- SAP HANA Cloud via HDI on Cloud Foundry')
        console.print()

        pers_choice = persistence
        if not pers_choice:
            choice_num  = IntPrompt.ask('       Choose', default=1)
            pers_choice = {1: 'jpa', 2: 'jdbc', 3: 'sap', 4: 'hana-cloud'}.get(choice_num, 'jpa')
        final_persistence = pers_choice

        final_hdi_service  = ''
        final_db_artifacts = db_artifacts or ''

        if final_persistence == 'hana-cloud':
            console.print()
            final_hdi_service = Prompt.ask(
                '  [cyan][6/7][/cyan] BTP HDI service instance name\n'
                '         [dim](the hdi-shared service instance in BTP — used in mta.yaml and application-cloud.properties)[/dim]',
                default=f'{final_artifact_id}-hdi'
            )

            console.print()
            wants_artifacts = Confirm.ask(
                '  [cyan][7/7][/cyan] Do you have .dtdbtable files to convert to HANA HDI artifacts?',
                default=False
            )
            if wants_artifacts:
                zip_input = Prompt.ask(
                    '         Path to ZIP file containing .dtdbtable (and optional .xlf) files'
                )
                final_db_artifacts = zip_input.strip().strip('"')

    # ── Build config ──────────────────────────────────────────────────────────
    output_path = Path(output).resolve() if output else source_path.parent / f'{final_artifact_id}-springboot'
    config = MigrationConfig(
        source_dir=source_path,
        output_dir=output_path,
        base_package=final_package,
        group_id=final_group_id,
        artifact_id=final_artifact_id,
        spring_boot_version=final_sb_version,
        java_version=final_java_version,
        persistence_mode=final_persistence,
        hdi_service_name=final_hdi_service,
        db_artifacts_zip=final_db_artifacts,
        scan_result=scan_result,
    )

    # ── Transform source files ────────────────────────────────────────────────
    output_path.mkdir(parents=True, exist_ok=True)

    # Exclude scaffold files (wrong base package — not legacy code)
    skipped_packages = scan_result['classified'].get('skipped', [])
    skipped_set      = set(skipped_packages)
    all_files        = [f for f in scan_result['all_java_files'] if f not in skipped_set]

    transformers = [
        LoggingTransformer(config),
        ImportTransformer(config),
        PersistenceTransformer(config),
        UtilsTransformer(config),
    ]
    reporter = Reporter(config)

    console.print(f'[bold]Migrating[/bold] -> [bold]{output_path}[/bold]')
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn('[progress.description]{task.description}'),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task('Transforming source files...', total=len(all_files))

        for java_file in all_files:
            rel_path = java_file.relative_to(source_path)

            with open(java_file, 'r', encoding='utf-8', errors='replace') as f:
                source = f.read()

            # Use the package declaration to place the file in the correct directory.
            # Flat legacy projects (no src/main/java tree) need this to land in the
            # right package subdirectory rather than directly under src/main/java/.
            pkg_match = re.search(r'^\s*package\s+([\w.]+)\s*;', source, re.MULTILINE)

            # Test files go to src/test/java; everything else to src/main/java
            path_str = str(java_file).replace('\\', '/')
            is_test  = (
                '/test/' in path_str
                or java_file.name.endswith(('Test.java', 'Tests.java', 'IT.java'))
            )
            java_root = Path('src') / ('test' if is_test else 'main') / 'java'

            if pkg_match:
                pkg_path = Path(*pkg_match.group(1).split('.'))
                out_file = output_path / java_root / pkg_path / java_file.name
            elif str(java_root) in str(rel_path).replace('\\', '/'):
                out_file = output_path / rel_path
            else:
                out_file = output_path / java_root / rel_path
            out_file.parent.mkdir(parents=True, exist_ok=True)

            result     = source
            file_todos = []
            for transformer in transformers:
                result, todos = transformer.transform(result, java_file, scan_result)
                file_todos.extend(todos)

            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(result)

            reporter.record_file(java_file, out_file.relative_to(output_path), file_todos)
            progress.advance(task)

    # ── Generate scaffold files ───────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn('{task.description}'), console=console) as progress:
        t = progress.add_task('Generating scaffold files...', total=None)
        PomGenerator(config).generate()
        AppClassGenerator(config).generate()
        PropertiesGenerator(config).generate()
        ManifestGenerator(config).generate()
        hdi_count = HdiGenerator(config).generate()
        _copy_resources(source_path, output_path)
        progress.update(t, completed=True)

    if hdi_count:
        console.print(f'  [green]✔[/green] Generated [bold]{hdi_count}[/bold] HDI table artifacts in [dim]db/src/[/dim]')

    # ── Write report ─────────────────────────────────────────────────────────
    report_path = output_path / 'migration-report.md'
    reporter.write(report_path)

    # ── Summary ──────────────────────────────────────────────────────────────
    console.print()
    summary = reporter.get_summary()
    console.print(Panel(
        f'[bold green]Migration complete[/bold green]\n\n'
        f'  Output:    [bold]{output_path}[/bold]\n'
        f'  Report:    [bold]{report_path}[/bold]\n\n'
        f'  [green]{summary["transformed"]} files transformed[/green]  .  '
        f'[yellow]{summary["todo_count"]} items need manual attention[/yellow]\n\n'
        f'  Next step: [dim]cd {output_path} && mvn compile[/dim]',
        border_style='green'
    ))


def _copy_resources(source_path: Path, output_path: Path):
    """Copy non-Java resources (properties, xml, etc.) to output."""
    import shutil
    resource_exts = {'.properties', '.xml', '.yaml', '.yml', '.json'}
    skip_dirs     = {'target', '.git', 'node_modules', '__pycache__'}

    for src_file in source_path.rglob('*'):
        if not (src_file.is_file() and src_file.suffix in resource_exts):
            continue
        if any(part in skip_dirs for part in src_file.parts):
            continue

        rel = src_file.relative_to(source_path)
        rel_str = str(rel).replace('\\', '/')

        # Skip resources from the nascent Spring Boot scaffold (main/ without src/ prefix).
        # These are not legacy resources — they belong to a pre-existing Spring Boot stub
        # and would overwrite the correctly generated application.properties.
        if rel_str.startswith('main/') or rel_str.startswith('test/'):
            continue

        dest = output_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest)


if __name__ == '__main__':
    main()
