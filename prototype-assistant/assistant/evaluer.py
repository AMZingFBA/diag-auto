"""Évaluation de bout en bout sur 10 phrases réalistes de diagnostiqueur (avec les fautes de
transcription entendues au test de Noah), avec le vrai cerveau : extraction immédiate + Claude
Code (abonnement) + garde-fous. Affiche ce qui est noté, la question posée et la latence de
chaque étape.

    python -m assistant.evaluer              (Claude Code, utilise l'abonnement)
    python -m assistant.evaluer --simulation (sans Claude)

Les phrases sont envoyées comme du texte écrit : la transcription n'est pas comptée ici (elle
prend ~2,3 s par phrase sur ce PC, mesurée à part sur l'enregistrement de Noah).
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import tempfile
from pathlib import Path

from .cerveau import CerveauClaudeCode
from .reglages import Reglages
from .session import Session
from .simulation import CerveauSimulation
from .transcription import TranscripteurSimulation

PHRASES = [
    "Ici c'est le séjour.",
    "Ce mur fait 4 m 50 de long, brique 30 cm, isolé par l'intérieur, il y a trois fenêtres en bois double vitrage, "
    "deux radiateurs à eau.",
    "Ictérieur.",
    "Roulant, roulant, roulant.",
    "BESSE !",
    "Je sais pas.",
    "Ça se meurt là, c'est du parpin de 20, isolé par l'extérieur avec 10 cm de polystyrène, il donne dehors.",
    "Celui-là, béton 18 cm, pas isolé, il donne sur le garage.",
    "La porte-fenêtre en alu, simple vitrage, volets roulants.",
    "Ici c'est la cuisine, la chaudière gaz à condensation de deux mille douze, et la VMC hygro B.",
]


def _s(valeur) -> str:
    return f"{valeur:.2f}".replace(".", ",") if isinstance(valeur, (int, float)) else "—"


async def evaluer(simulation: bool) -> dict:
    dossier = Path(tempfile.mkdtemp(prefix="diagauto-evaluation-"))
    if simulation:
        cerveau = veille = CerveauSimulation()
    else:
        cerveau = CerveauClaudeCode(dossier / "claude-reponses")
        veille = CerveauSimulation()  # pas de veille ici : aucune image
    reglages = Reglages(cerveau="simulation" if simulation else "claude", transcription="simulation",
                        dossier_sessions=dossier, veille_s=10_000, questions_par_minute=60)
    session = Session("evaluation", dossier, cerveau, veille, TranscripteurSimulation(), reglages)
    recus: list[dict] = []

    async def envoyer(message: dict) -> None:
        recus.append(message)

    session.envoyer = envoyer
    print(f"Cerveau : {cerveau.nom}\nDémarrage…", flush=True)
    await session.demarrer()
    await session._pret.wait()
    print()
    posees: list[tuple[str, str]] = []  # (pièce, question)
    for numero, phrase in enumerate(PHRASES, 1):
        avant = len(recus)
        await session.recevoir_controle({"type": "texte", "texte": phrase})
        await asyncio.sleep(0.05)
        while session.occupe:
            await asyncio.sleep(0.05)
        mesure = session.mesures[-1]
        nouveaux = recus[avant:]
        notes = [f"{r.get('element') or ''}{' ×' + str(r['nombre']) if (r.get('nombre') or 1) > 1 else ''} {r['champ']} = {r.get('valeur') or 'sans objet'}"
                 for m in nouveaux if m["type"] == "actions" for r in m["resultats"]
                 if r["statut"] == "accepte" and r["outil"] in ("enregistrer_reponse", "marquer_sans_objet")]
        questions = [m["texte"] for m in nouveaux if m["type"] == "dire"]
        posees += [(str(session.checklist.piece_courante), q) for q in questions]
        print(f"{numero:2d}. « {phrase} »")
        print(f"    noté   : {', '.join(notes) or 'rien'}")
        print(f"    dit    : {' / '.join(questions) or '(rien)'}")
        print(f"    temps  : extraction {mesure.get('extraction_ms')} ms | bip {_s(mesure.get('bip_s'))} s"
              f" | question {_s(mesure.get('cerveau_dire_s'))} s | Claude total {_s(mesure.get('cerveau_total_s'))} s", flush=True)
    bilan = await session.terminer()
    print("\nÉtat final :")
    for element in session.checklist.elements:
        valeurs = ", ".join(f"{c} = {v[-1].valeur}" for c, v in element.valeurs.items())
        nombre = f" ×{element.nombre}" if element.nombre > 1 else ""
        print(f"  {element.id}{nombre} {element.description} : {valeurs or '—'}")

    def mediane(cle: str) -> str:
        valeurs = [m[cle] for m in session.mesures if isinstance(m.get(cle), (int, float))]
        return _s(statistics.median(valeurs)) if valeurs else "—"

    questions = [m["texte"] for m in recus if m["type"] == "dire"]
    print("\nRésumé :")
    print(f"  valeurs notées {bilan['acceptees']}, refusées {bilan['refusees']}, questions posées {len(questions)}")
    print(f"  questions avec « répét » / « pardon » : {sum(('répét' in q.lower()) or ('pardon' in q.lower()) for q in questions)}"
          f" ; questions doubles (2 « ? ») : {sum(q.count('?') > 1 for q in questions)}"
          f" ; même question redemandée dans la même pièce : {len(posees) - len(set(posees))}")
    print(f"  latence médiane : extraction {mediane('extraction_ms')} ms, bip {mediane('bip_s')} s, "
          f"question {mediane('cerveau_dire_s')} s, Claude total {mediane('cerveau_total_s')} s")
    print("  + sur téléphone : ~0,7 s de silence de fin de phrase et ~2,3 s de transcription (mesurés à part)")
    return bilan


def main() -> None:
    parser = argparse.ArgumentParser(description="Évaluation de l'assistant sur 10 phrases réalistes")
    parser.add_argument("--simulation", action="store_true", help="sans Claude (règles seulement)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(evaluer(args.simulation))


if __name__ == "__main__":
    main()
