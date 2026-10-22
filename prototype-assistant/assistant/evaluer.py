"""Évaluation de bout en bout sur une pièce complète à 4 murs (étape 2 de Noah) : extraction
immédiate + parcours du serveur + Claude Code (abonnement) quand les règles n'ont pas compris.
Affiche, phrase par phrase, ce qui est noté, la question posée et la latence de chaque étape.

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

# (phrase du diagnostiqueur, question attendue juste après) : une pièce à 4 murs, puis la pièce suivante.
# Les tests (tests/test_dialogue.py) vérifient ce même parcours question par question.
PIECE_A_4_MURS = [
    ("Ici c'est le séjour.", "Décrivez le premier mur."),
    ("Ce mur donne dehors, brique 30 cm, isolé par l'intérieur.", "Un autre mur dans cette pièce ?"),
    ("Oui, celui-ci donne sur une pièce chauffée.", "Un autre mur dans cette pièce ?"),  # mur intérieur : rien d'autre
    ("Oui, en parpaing de 20, non isolé, sur le garage.", "Un autre mur dans cette pièce ?"),
    ("Oui, le quatrième mur donne dehors.", "Le mur 4 est en quoi ?"),
    ("Brique.", "Quelle épaisseur ?"),
    ("30 centimètres.", "Il est isolé ?"),
    ("Je ne sais pas.", "Un autre mur dans cette pièce ?"),
    ("Non, c'est tout.", "Au-dessus du plafond : combles, terrasse ou logement ?"),
    ("Des combles perdus, isolés avec 30 cm de laine de verre.", "Sous le plancher : terre-plein, vide sanitaire, cave ou logement ?"),
    ("Terre-plein, pas isolé.", "Des fenêtres dans cette pièce ?"),
    ("En tout trois fenêtres, toutes pareilles, en PVC double vitrage.", "Les 3 fenêtres : des volets ?"),
    ("Volets roulants.", "D'autres fenêtres, ou une porte vers l'extérieur ?"),
    ("Non.", "Des radiateurs dans cette pièce ?"),
    ("Oui, deux, à eau.", "Quel est le chauffage principal ?"),
    ("Une chaudière gaz à condensation de 2015.", "Et l'eau chaude, comment est-elle produite ?"),
    ("Par la chaudière.", "Ventilation : VMC ou naturelle ?"),
    ("VMC hygro B.", "Vos radiateurs à eau sont basse ou haute température ?"),
    ("Je ne sais pas.", "Les radiateurs datent de quand, à peu près ?"),
    ("Aucune idée.", "Pièce terminée. Quelle est la pièce suivante ?"),
    ("La cuisine.", "Décrivez le premier mur."),
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
    conformes = 0
    for numero, (phrase, attendue) in enumerate(PIECE_A_4_MURS, 1):
        avant = len(recus)
        await session.recevoir_controle({"type": "texte", "texte": phrase})
        await asyncio.sleep(0.05)
        while session.occupe:
            await asyncio.sleep(0.05)
        mesure = session.mesures[-1]
        nouveaux = recus[avant:]
        notes = [f"{r.get('element') or ''}{' ×' + str(r['nombre']) if (r.get('nombre') or 1) > 1 else ''} {r['champ'] or r['outil']}"
                 f" = {r.get('valeur') or ''}".rstrip(" =")
                 for m in nouveaux if m["type"] == "actions" for r in m["resultats"]
                 if r["statut"] == "accepte" and r["outil"] in ("enregistrer_reponse", "marquer_sans_objet", "cloturer", "copier")]
        questions = [m["texte"] for m in nouveaux if m["type"] == "dire"]
        conformes += questions == [attendue]
        claude = f" | Claude appelé : {_s(mesure.get('cerveau_total_s'))} s" if "cerveau_total_s" in mesure else ""
        print(f"{numero:2d}. « {phrase} »")
        print(f"    noté   : {', '.join(notes) or 'rien'}")
        print(f"    dit    : {' / '.join(questions) or '(rien)'}{'' if questions == [attendue] else f'   ← attendu : {attendue}'}")
        print(f"    temps  : extraction {mesure.get('extraction_ms')} ms | question {_s(mesure.get('question_s'))} s{claude}", flush=True)
    bilan = await session.terminer()

    def mediane(cle: str) -> str:
        valeurs = [m[cle] for m in session.mesures if isinstance(m.get(cle), (int, float))]
        return _s(statistics.median(valeurs)) if valeurs else "—"

    questions = [m["texte"] for m in recus if m["type"] == "dire"]
    reviennent = {"Un autre mur dans cette pièce ?", "Décrivez le premier mur.", "D'autres fenêtres, ou une porte vers l'extérieur ?"}
    uniques = [q for q in questions if q not in reviennent]
    print("\nRésumé :")
    print(f"  questions conformes au parcours : {conformes}/{len(PIECE_A_4_MURS)} ; valeurs notées {bilan['acceptees']},"
          f" refusées {bilan['refusees']} ; taux de remplissage du séjour {round(100 * session.checklist.taux_remplissage('sejour'))} %")
    print(f"  questions avec « répét » / « pardon » : {sum(('répét' in q.lower()) or ('pardon' in q.lower()) for q in questions)}"
          f" ; questions doubles (2 « ? ») : {sum(q.count('?') > 1 for q in questions)}"
          f" ; même question reposée : {len(uniques) - len(set(uniques))} (hors celles qui reviennent à chaque mur ou pièce)")
    print(f"  Claude appelé pour {sum('cerveau_total_s' in m for m in session.mesures)} phrase(s) non comprise(s) sur {len(PIECE_A_4_MURS)},"
          f" et {bilan['relectures_claude']} relecture(s) en arrière-plan de phrases longues")
    print(f"  latence médiane : extraction {mediane('extraction_ms')} ms, question {mediane('question_s')} s")
    print("  + sur téléphone : ~0,7 s de silence de fin de phrase et ~2,3 s de transcription (mesurés à part)")
    return bilan


def main() -> None:
    parser = argparse.ArgumentParser(description="Évaluation de l'assistant sur une pièce complète à 4 murs")
    parser.add_argument("--simulation", action="store_true", help="sans Claude (règles et parcours seulement)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(evaluer(args.simulation))


if __name__ == "__main__":
    main()
