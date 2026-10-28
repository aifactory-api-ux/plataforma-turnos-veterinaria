"""Configuración de pytest compartida por toda la suite.

Mientras la suite todavía no tiene archivos de test (fase de andamiaje),
pytest termina con el código 5 ("no se recolectó ningún test"). Este módulo
normaliza ese caso a un cierre correcto para que la verificación del andamiaje
no falle por una suite todavía vacía. Cuando existen tests, el hook no
interviene y el código de salida es el habitual de pytest.
"""

from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent / "tests"


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Cierra la sesión con código correcto si aún no hay tests en el repositorio.

    Args:
        session: Sesión de pytest en curso.
        exitstatus: Código de salida calculado por pytest.
    """
    if exitstatus != pytest.ExitCode.NO_TESTS_COLLECTED:
        return
    if any(TESTS_DIR.glob("test_*.py")):
        return
    session.exitstatus = pytest.ExitCode.OK
