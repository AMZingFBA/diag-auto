"""Conversions des valeurs texte LICIEL (virgule décimale, Vrai/Faux…)."""

from __future__ import annotations


def nombre(texte: str | None) -> float | None:
    """« 284,20 », « 10.2 », « 47 629 » -> float ; vide ou illisible -> None."""
    if texte is None:
        return None
    t = texte.strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def booleen(texte: str | None) -> bool | None:
    """« Vrai »/« Faux », « True »/« False », « 1 »/« 0 » -> bool ; autre -> None."""
    t = (texte or "").strip().lower()
    if t in ("vrai", "true", "1"):
        return True
    if t in ("faux", "false", "0"):
        return False
    return None


def format_fr(valeur: float | None, decimales: int = 2) -> str:
    """284.2 -> « 284,20 » ; None -> « - »."""
    if valeur is None:
        return "-"
    return f"{valeur:.{decimales}f}".replace(".", ",")
