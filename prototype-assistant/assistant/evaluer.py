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
import json
import statistics
import sys
import tempfile
from pathlib import Path

from .cerveau import CerveauClaudeCode
from .checklist import Checklist
from .repetition import mots_repetes
from .extraction import Cible, question_posee
from .reglages import Reglages
from .session import Session
from .simulation import CerveauSimulation
from .transcription import TranscripteurSimulation

# (phrase du diagnostiqueur, question attendue juste après) : une pièce à 4 murs, puis la pièce suivante.
# Les tests (tests/test_dialogue.py) vérifient ce même parcours question par question.
PIECE_A_4_MURS = [
    ("Ici c'est le séjour.", "Décrivez le premier mur."),
    # « D'autres murs qui donnent dehors… ? » : une fois, puis seulement après un nouveau mur dehors ou sur un local non
    # chauffé (test de Noah du 22/10 après-midi : « Un autre mur dans cette pièce ? » posé 10 fois).
    ("Ce mur donne dehors, brique 30 cm, isolé par l'intérieur.", "D'autres murs sur l'extérieur ou un local non chauffé ?"),
    ("Oui, en parpaing de 20, non isolé, sur le garage.", "D'autres murs sur l'extérieur ou un local non chauffé ?"),
    ("Oui, le troisième mur donne dehors.", "Ce mur est en quoi ?"),  # jamais « le mur 3 » (étape 5)
    ("Brique.", "Quelle épaisseur ?"),
    ("30 centimètres.", "Il est isolé ?"),
    ("Je ne sais pas.", "D'autres murs sur l'extérieur ou un local non chauffé ?"),
    # Un mur sur une pièce chauffée : rien d'autre à demander, et pas de nouvelle question sur les murs.
    ("Oui, le dernier mur donne sur une pièce chauffée.", "Au-dessus du plafond : combles, terrasse ou logement ?"),
    ("Des combles perdus, isolés avec 30 cm de laine de verre.", "Sous le plancher : terre-plein, vide sanitaire, cave ou logement ?"),
    ("Terre-plein, pas isolé.", "Des fenêtres dans cette pièce ?"),
    ("En tout trois fenêtres, toutes pareilles, en PVC double vitrage.", "Les 3 fenêtres : des volets ?"),
    ("Volets roulants.", "D'autres fenêtres, ou une porte vers l'extérieur ?"),
    ("Non.", "Des radiateurs dans cette pièce ?"),
    ("Oui, deux, à eau.", "Quel est le chauffage principal ?"),
    ("Une chaudière gaz à condensation de 2015.", "Et l'eau chaude, comment est-elle produite ?"),
    ("Par la chaudière.", "Ventilation : VMC ou naturelle ?"),
    # Date et température des radiateurs : plus jamais demandées (étape 4), mais notées si elles sont dites.
    ("VMC hygro B.", "Pièce terminée. Quelle est la pièce suivante ?"),
    ("La cuisine.", "Décrivez le premier mur."),
]


# Réponses que les règles ne peuvent pas trancher seules : Claude doit les interpréter par rapport à la
# question posée (étape 3 de Noah). (champ visé par la dernière question, question, transcription)
CAS_DIFFICILES = [
    ("PL1.donne_sur", "Au-dessus du plafond : combles, terrasse ou logement ?", "Au-dessus c'est le voisin, il est chauffé."),
    ("PB1.donne_sur", "Sous le plancher : terre-plein, vide sanitaire, cave ou logement ?", "En dessous y a le parking de l'immeuble."),
    ("E1.type", "Les 2 radiateurs : à eau ou électrique ?", "Oh !"),
    ("E1.type", "Les 2 radiateurs : à eau ou électrique ?", "Ils sont branchés sur la chaudière."),
    ("M1.materiau", "Le mur avec la télé est en quoi ?", "C'est du, euh, comment on dit, du bloc creux."),
    ("F1.menuiserie", "Les 3 fenêtres : PVC, bois ou alu ?", "Du plastique blanc."),
]


# Étape 7 : une VRAIE conversation. Une visite en cours (séjour décrit, cuisine commencée), puis 30 phrases libres que
# des règles ne peuvent pas prévoir : Claude, cerveau de chaque phrase, doit y répondre et reprendre la visite.
MISE_EN_PLACE = [
    "Ici c'est le séjour.",
    "Ce mur donne dehors, brique 30 cm, isolé par l'intérieur, il y a deux fenêtres PVC double vitrage dessus.",
    "Un autre mur donne sur le voisin.",
    "Pas d'autre mur.",
    "Au-dessus, des combles perdus isolés avec 30 cm de laine de verre.",
    "Terre-plein, pas isolé.",
    "Volets roulants.",
    "Pas d'autre fenêtre.",
    "Deux radiateurs à eau.",
    "Une chaudière gaz à condensation de 2015.",
    "On passe dans la cuisine.",
    "Ce mur donne dehors, parpaing de 20, non isolé.",
]
# (catégorie, phrase)
CONVERSATION_LIBRE = [
    ("question générale", "C'est quoi un pont thermique ?"),
    ("question générale", "Comment se construit une maison ?"),
    ("question générale", "Ça sert à quoi une VMC ?"),
    ("question générale", "C'est quoi la différence entre une isolation par l'intérieur et par l'extérieur ?"),
    ("question générale", "Un DPE, c'est valable combien de temps ?"),
    ("question générale", "Pourquoi tu me demandes l'épaisseur des murs ?"),
    ("hors sujet", "Comment ça va ?"),
    ("hors sujet", "Tu m'entends bien ?"),
    ("hors sujet", "Il fait drôlement chaud dans cette cuisine."),
    ("hors sujet", "Tu es qui, toi ?"),
    ("hors sujet", "Merci, tu m'aides bien."),
    ("navigation", "On fait une pause, je prends un appel."),
    ("navigation", "Tu as noté quoi pour le séjour ?"),
    ("navigation", "C'est bon, on reprend."),
    ("navigation", "Attends, reviens au séjour."),
    ("navigation", "Bon, on retourne dans la cuisine."),
    ("navigation", "On a fini la cuisine, on passe à la chambre."),
    ("correction", "Non, le premier mur du séjour, c'est du parpaing, pas de la brique."),
    ("correction", "Je me suis trompé, il y a trois radiateurs dans le séjour, pas deux."),
    ("correction", "En fait, la chaudière date de 2012."),
    ("correction", "Oublie ce que je viens de dire sur la chaudière, c'était bien 2015."),
    ("correction", "Ce mur de la chambre, il est orienté plein sud."),
    ("récapitulatif", "Où on en est ?"),
    ("récapitulatif", "Il manque quoi dans cette pièce ?"),
    ("récapitulatif", "Rappelle-moi ce que j'ai dit sur le chauffage."),
    ("récapitulatif", "Combien de fenêtres on a vues jusqu'ici ?"),
    ("récapitulatif", "Tu as noté quoi pour la cuisine ?"),
    ("description libre", "Bon alors là c'est un mur un peu bizarre, moitié pierre moitié brique, je dirais 50 centimètres, il donne sur la rue."),
    ("description libre", "Là il y a une vieille fenêtre en bois, simple vitrage, sans volet, elle ferme mal."),
    ("description libre", "Le radiateur de la chambre est électrique, un vieux grille-pain."),
]


async def evaluer_conversation(sortie: Path | None) -> None:
    """Les 30 phrases libres avec le vrai Claude (abonnement), après la mise en place de la visite. Affiche, pour chaque
    phrase, ce que l'assistant répond, ce qui est noté, et les temps (première phrase dite, réponse complète)."""
    dossier = Path(tempfile.mkdtemp(prefix="diagauto-conversation-"))
    cerveau = CerveauClaudeCode(dossier / "claude-reponses")
    reglages = Reglages(cerveau="claude", transcription="simulation", dossier_sessions=dossier, veille_s=10_000, questions_par_minute=60,
                        conversation="claude")
    session = Session("conversation", dossier, cerveau, CerveauSimulation(), TranscripteurSimulation(), reglages)
    recus: list[dict] = []
    lignes: list[str] = []

    async def envoyer(message: dict) -> None:
        recus.append(message)

    def ecrire(texte: str = "") -> None:
        print(texte, flush=True)
        lignes.append(texte)

    journal = dossier / "journal.jsonl"

    async def phrase(texte: str) -> tuple[list[str], dict[str, list[str]], dict]:
        avant, lignes_avant = len(recus), len(journal.read_text(encoding="utf-8").splitlines()) if journal.exists() else 0
        await session.recevoir_controle({"type": "texte", "texte": texte})
        await asyncio.sleep(0.05)
        while session.occupe:
            await asyncio.sleep(0.05)
        nouveaux = recus[avant:]
        dits = [m["texte"] for m in nouveaux if m["type"] == "dire"]
        notes: dict[str, list[str]] = {"règles": [], "Claude": []}
        for m in nouveaux:
            if m["type"] == "actions":
                notes["règles" if m["source"] == "extraction" else "Claude"] += [
                    " ".join(str(x) for x in (r["outil"], r.get("element"), r.get("champ"), r.get("valeur") or r.get("description")
                                              or r.get("nombre")) if x) for r in m["resultats"] if r["statut"] == "accepte"]
        for ligne in journal.read_text(encoding="utf-8").splitlines()[lignes_avant:]:
            if '"commandes"' in ligne and (d := json.loads(ligne))["evenement"] == "commandes":
                notes["Claude"] += d["commandes"]
        return dits, notes, session.mesures[-1]

    session.envoyer = envoyer
    print(f"Cerveau : {cerveau.nom}\nDémarrage…", flush=True)
    await session.demarrer()
    await session._pret.wait()
    ecrire("## Mise en place de la visite\n")
    repris: list[int] = []  # étape 9 : mots de sa phrase repris dans la réponse à une description (objectif : aucun)

    def repetes(texte: str, dits: list[str]) -> str:
        if question_posee(texte):
            return ""
        mots = mots_repetes(texte, " ".join(dits))
        repris.append(len(mots))
        return f" — mots repris : {', '.join(mots)}" if mots else ""

    for texte in MISE_EN_PLACE:
        dits, _, _ = await phrase(texte)
        ecrire(f"- « {texte} » → « {' '.join(dits) or '(bip)'} »{repetes(texte, dits)}")
    ecrire("\n## 30 phrases libres\n")
    premieres, totaux = [], []
    for numero, (categorie, texte) in enumerate(CONVERSATION_LIBRE, 1):
        dits, notes, mesure = await phrase(texte)
        premiere, total = mesure.get("question_s"), mesure.get("cerveau_total_s")
        premieres += [premiere] if isinstance(premiere, (int, float)) else []
        totaux += [total] if isinstance(total, (int, float)) else []
        ecrire(f"{numero}. *{categorie}* — « {texte} »")
        ecrire(f"   - **Assistant** : « {' '.join(dits) or '(rien)'} »{repetes(texte, dits)}")
        for qui, faites in notes.items():
            if faites:
                ecrire(f"   - {'pré-rempli par les règles' if qui == 'règles' else 'Claude'} : {' ; '.join(faites)}")
        ecrire(f"   - temps : première phrase dite {_s(premiere)} s, réponse complète de Claude {_s(total)} s"
               + (" — en pause" if session.en_pause else ""))
    await session.terminer()
    ecrire("\n## Résumé\n")
    ecrire(f"- réponses non vides : {sum(1 for _ in premieres)}/{len(CONVERSATION_LIBRE)}")
    if premieres:
        ecrire(f"- première phrase dite : médiane {_s(statistics.median(premieres))} s, pire {_s(max(premieres))} s "
               f"(après la fin de phrase ; + 0,7 s de silence et ~0,05 s de transcription au téléphone)")
    if totaux:
        ecrire(f"- réponse complète de Claude : médiane {_s(statistics.median(totaux))} s")
    if repris:
        ecrire(f"- mots de sa phrase repris dans la réponse à une description : {_s(statistics.mean(repris))} par réponse en "
               f"moyenne, sur {len(repris)} réponses ({sum(1 for n in repris if n)} en reprennent au moins un)")
    if sortie:
        sortie.write_text("\n".join(lignes) + "\n", encoding="utf-8")


def _sejour_en_cours() -> Checklist:
    c = Checklist()
    c.definir_piece("Séjour", 0)
    c.signaler_element("mur", "le mur avec la télé", 1)
    c.signaler_element("fenetre", "les 3 fenêtres", 1, nombre=3)
    c.signaler_element("emetteur", "les 2 radiateurs", 1, nombre=2)
    return c


async def evaluer_comprehension() -> None:
    """Chaque cas difficile part d'un séjour en cours, avec la question posée juste avant."""
    dossier = Path(tempfile.mkdtemp(prefix="diagauto-comprehension-"))
    cerveau = CerveauClaudeCode(dossier / "claude-reponses")
    reglages = Reglages(cerveau="claude", transcription="simulation", dossier_sessions=dossier, veille_s=10_000, questions_par_minute=60,
                        conversation="rapide")  # Claude seulement pour la phrase difficile
    session = Session("comprehension", dossier, cerveau, CerveauSimulation(), TranscripteurSimulation(), reglages)
    recus: list[dict] = []

    async def envoyer(message: dict) -> None:
        recus.append(message)

    session.envoyer = envoyer
    print(f"Cerveau : {cerveau.nom}\nDémarrage…\n", flush=True)
    await session.demarrer()
    await session._pret.wait()
    for code, question, phrase in CAS_DIFFICILES:
        session.checklist = _sejour_en_cours()
        session._cible = Cible.depuis_code(code, session.checklist)
        session._derniere_question_texte = f"{code} : « {question} »"
        avant = len(recus)
        await session.recevoir_controle({"type": "texte", "texte": phrase})
        await asyncio.sleep(0.05)
        while session.occupe:
            await asyncio.sleep(0.05)
        element_id, champ = code.split(".")
        valeur = session.checklist.trouver_element(element_id).valeur(champ)
        dits = [m["texte"] for m in recus[avant:] if m["type"] == "dire"]
        mesure = session.mesures[-1]
        print(f"« {question} »  →  « {phrase} »")
        print(f"    noté : {valeur.valeur + (' (' + valeur.note + ')' if valeur.note else '') if valeur else 'rien'}")
        print(f"    dit  : {' / '.join(dits) or '(rien)'} | Claude {_s(mesure.get('cerveau_total_s'))} s", flush=True)
    await session.terminer()


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
                        dossier_sessions=dossier, veille_s=10_000, questions_par_minute=60,
                        conversation="rapide")  # le parcours mot pour mot ; la conversation : --conversation
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
    reviennent = {"D'autres murs sur l'extérieur ou un local non chauffé ?", "Décrivez le premier mur.",
                  "D'autres fenêtres, ou une porte vers l'extérieur ?"}
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
    parser.add_argument("--comprehension", action="store_true", help="réponses difficiles interprétées par Claude selon la question")
    parser.add_argument("--conversation", action="store_true", help="30 phrases libres : Claude cerveau de chaque phrase (étape 7)")
    parser.add_argument("--sortie", type=Path, help="fichier Markdown où écrire le résultat de --conversation")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.conversation:
        asyncio.run(evaluer_conversation(args.sortie))
    else:
        asyncio.run(evaluer_comprehension() if args.comprehension else evaluer(args.simulation))


if __name__ == "__main__":
    main()
