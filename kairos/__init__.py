"""Kairos — capture de dislocations de prix."""
import sys

__version__ = "0.1.0"

# Python 3.10 minimum. Le Python livre avec macOS est un 3.9 : creer
# l'environnement virtuel avec lui produit sinon une erreur incomprehensible
# (`dataclass() got an unexpected keyword argument 'slots'`) tres loin de sa cause.
if sys.version_info < (3, 10):
    raise RuntimeError(
        f"Kairos exige Python 3.10 ou superieur (detecte : "
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}).\n"
        "\n"
        "Cause la plus probable : l'environnement virtuel a ete cree avec le Python\n"
        "livre par macOS (3.9) au lieu de celui installe par Homebrew.\n"
        "\n"
        "Correction :\n"
        "    deactivate\n"
        "    rm -rf .venv\n"
        "    brew install python@3.12\n"
        "    $(brew --prefix)/bin/python3.12 -m venv .venv\n"
        "    source .venv/bin/activate\n"
        "    python --version      # doit afficher 3.12.x\n"
    )
