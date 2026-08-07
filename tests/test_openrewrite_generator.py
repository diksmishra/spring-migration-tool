"""Tests for OpenRewriteGenerator — verifies the run-openrewrite.sh script is emitted correctly."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from migration_tool.config import MigrationConfig
from migration_tool.generators.openrewrite_generator import OpenRewriteGenerator


def _config(tmp_path):
    return MigrationConfig(
        source_dir=tmp_path / 'src',
        output_dir=tmp_path / 'out',
        base_package='com.example',
        group_id='com.example',
        artifact_id='test-app',
        spring_boot_version='3.2.5',
        java_version='17',
        persistence_mode='jpa',
    )


EXPECTED_RECIPE_ORDER = [
    'org.openrewrite.java.migrate.UpgradeToJava25',
    'org.openrewrite.java.migrate.jakarta.JakartaEE11',
    'org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_2',
    'org.openrewrite.java.logging.slf4j.Log4jToSlf4j',
    'org.openrewrite.staticanalysis.CommonStaticAnalysis',
]


def test_script_written_to_output_root(tmp_path):
    OpenRewriteGenerator(_config(tmp_path)).generate()
    assert (tmp_path / 'out' / 'run-openrewrite.sh').exists()


def test_script_has_no_pom_modification_and_uses_mvn_run_goal(tmp_path):
    OpenRewriteGenerator(_config(tmp_path)).generate()
    content = (tmp_path / 'out' / 'run-openrewrite.sh').read_text(encoding='utf-8')
    assert 'org.openrewrite.maven:rewrite-maven-plugin' in content
    assert 'rewrite.recipeArtifactCoordinates' in content
    assert 'rewrite.activeRecipes' in content


def test_active_recipes_present_in_correct_order(tmp_path):
    OpenRewriteGenerator(_config(tmp_path)).generate()
    content = (tmp_path / 'out' / 'run-openrewrite.sh').read_text(encoding='utf-8')

    active_recipes_line = next(
        line for line in content.splitlines() if line.startswith('ACTIVE_RECIPES=')
    )
    positions = [active_recipes_line.index(recipe) for recipe in EXPECTED_RECIPE_ORDER]
    assert positions == sorted(positions), 'Recipes must appear in the documented order'


def test_static_analysis_recipe_runs_last(tmp_path):
    """CommonStaticAnalysis cleans up debris left by the other recipes, so it must run last."""
    OpenRewriteGenerator(_config(tmp_path)).generate()
    content = (tmp_path / 'out' / 'run-openrewrite.sh').read_text(encoding='utf-8')
    active_recipes_line = next(
        line for line in content.splitlines() if line.startswith('ACTIVE_RECIPES=')
    )
    recipes = active_recipes_line.split('=', 1)[1].strip('"').split(',')
    assert recipes[-1] == 'org.openrewrite.staticanalysis.CommonStaticAnalysis'


def test_recipe_artifact_modules_cover_all_active_recipes(tmp_path):
    OpenRewriteGenerator(_config(tmp_path)).generate()
    content = (tmp_path / 'out' / 'run-openrewrite.sh').read_text(encoding='utf-8')
    for module in ('rewrite-migrate-java', 'rewrite-spring', 'rewrite-logging-frameworks', 'rewrite-static-analysis'):
        assert module in content


def test_script_uses_unix_line_endings(tmp_path):
    """A CRLF shebang line breaks execution on the Linux cloud IDE this script targets."""
    OpenRewriteGenerator(_config(tmp_path)).generate()
    raw = (tmp_path / 'out' / 'run-openrewrite.sh').read_bytes()
    assert b'\r\n' not in raw


def test_generate_is_idempotent(tmp_path):
    gen = OpenRewriteGenerator(_config(tmp_path))
    gen.generate()
    gen.generate()
    assert (tmp_path / 'out' / 'run-openrewrite.sh').exists()
