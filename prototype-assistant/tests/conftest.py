import sys
from pathlib import Path

# Rend le paquet « assistant » importable quand pytest est lancé depuis la racine du dépôt.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
