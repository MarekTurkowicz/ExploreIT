from typer.testing import CliRunner

from exploreit import __version__
from exploreit.cli import app


def test_version_command_prints_version() -> None:
    result = CliRunner().invoke(app, ["version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout
