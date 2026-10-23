"""Évaluation de bout en bout sur une visite de deux pièces décrite par côté (étapes 2 et 13 de Noah) : extraction
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

# Étape 13 (Noah) : le DPE décrit l'enveloppe du logement, par côté, pas pièce par pièce ; la pièce où l'on est ne compte
# pas (« qu'on soit dans le séjour ou la chambre, pour le DPE on s'en fiche ») et n'est jamais demandée. Une visite
# téléphone en main : (phrase du diagnostiqueur, cap de la caméra pendant la phrase — 0 = nord, 90 = est — ou None,
# question attendue juste après, ou None si l'assistant n'a rien à demander). Les tests (tests/test_dialogue.py)
# vérifient ce même parcours question par question.
VISITE_PAR_COTES = [
    ("On commence.", None, "Ce mur donne sur quoi ?"),  # « ce mur donne sur quoi ? », jamais « dans quelle pièce ? »
    ("Sur la rue, brique 30 cm, isolé par l'intérieur.", 272, "Des fenêtres ou une porte sur ce mur ?"),
    ("Oui, trois fenêtres PVC double vitrage.", 272, "Les 3 fenêtres : des volets ?"),
    # Mur par mur (retour de Noah du 22/10 au soir) : chaque côté a sa question, et il est fini avant le suivant.
    ("Volets roulants.", 272, "Et le mur nord, il donne sur quoi ?"),
    ("Le voisin.", 0, "Et le mur sud, il donne sur quoi ?"),  # un voisin : rien d'autre
    ("La cour, brique 30 cm, isolé par l'intérieur, avec une porte-fenêtre alu double vitrage.", 180,
     "Cette porte-fenêtre : des volets ?"),
    ("Aucun.", 180, "Et le mur est, il donne sur quoi ?"),
    # Un mur en partie sur la cage d'escalier, en partie sur le voisin : deux parties du même côté.
    ("En partie sur la cage d'escalier, en partie sur le voisin.", 90, "Le mur est côté parties communes est en quoi ?"),
    ("Parpaing de 20, pas isolé.", 90, "Des fenêtres ou une porte sur ce mur ?"),
    # Sur un mur qui donne sur les parties communes, la porte donne sur le palier : déduit, pas demandé.
    ("La porte d'entrée, en bois.", 90, "Un autre mur autour du logement, à me montrer ?"),
    # Une maison peut avoir plus de quatre murs : il le montre à la caméra, qui donne son côté.
    ("Oui, celui-ci donne sur le garage, parpaing 20, pas isolé.", 200, "Des fenêtres ou une porte sur ce mur ?"),
    ("Non.", 200, "Un autre mur autour du logement, à me montrer ?"),
    ("Non, c'est tout.", None, "Au-dessus du logement : combles, terrasse ou un autre logement ?"),
    ("Des combles perdus, isolés avec 30 cm de laine de verre.", 270,
     "Sous le logement : terre-plein, vide sanitaire, cave ou un autre logement ?"),
    ("Terre-plein, pas isolé.", 270, "Quel est le chauffage principal ?"),
    ("Une chaudière gaz à condensation de 2015.", 90, "Et les radiateurs : à eau ou électriques ?"),
    ("À eau.", 90, "Et l'eau chaude, comment est-elle produite ?"),
    ("Par la chaudière.", 90, "Ventilation : VMC ou naturelle ?"),
    # Date et température des radiateurs : jamais demandées (étape 4), mais notées si elles sont dites.
    ("VMC hygro B.", 90, "C'est complet pour le DPE."),
    # Il continue dans une autre pièce : rien n'est redemandé des murs, du plafond ni du plancher. Ce qu'il dit de nouveau
    # est rangé : face au nord, « le mur de gauche » est le mur ouest, ici sur le voisin (une autre partie du mur ouest).
    ("On passe dans la chambre.", 0, None),
    ("Le mur de gauche donne sur le voisin.", 0, None),
    ("Encore une fenêtre en bois, simple vitrage, sans volet.", 182, None),
]


async def phrase_filmee(session: Session, texte: str, cap: float | None, t: float) -> None:
    """Une phrase dite en filmant : la boussole du téléphone (cap et lacet) à l'instant de la phrase, puis la phrase."""
    session.t_video = t
    if cap is not None:
        await session.recevoir_controle({"type": "capteurs", "t": t, "cap": cap, "lacet": cap, "inclinaison": 90.0})
    await session.recevoir_controle({"type": "texte", "texte": texte})


# Réponses que les règles ne peuvent pas trancher seules : Claude doit les interpréter par rapport à la
# question posée (étape 3 de Noah). (champ visé par la dernière question, question, transcription)
CAS_DIFFICILES = [
    ("PL1.donne_sur", "Au-dessus du logement : combles, terrasse ou un autre logement ?", "Au-dessus c'est le voisin, il est chauffé."),
    ("PB1.donne_sur", "Sous le logement : terre-plein, vide sanitaire, cave ou un autre logement ?", "En dessous y a le parking de l'immeuble."),
    ("E1.type", "Les 2 radiateurs : à eau ou électrique ?", "Oh !"),
    ("E1.type", "Les 2 radiateurs : à eau ou électrique ?", "Ils sont branchés sur la chaudière."),
    ("M1.materiau", "Le mur avec la télé est en quoi ?", "C'est du, euh, comment on dit, du bloc creux."),
    ("F1.menuiserie", "Les 3 fenêtres : PVC, bois ou alu ?", "Du plastique blanc."),
]


# Étape 7 : une VRAIE conversation. Une visite en cours (séjour décrit, cuisine commencée), puis 30 phrases libres que
# des règles ne peuvent pas prévoir : Claude, cerveau de chaque phrase, doit y répondre et reprendre la visite.
MISE_EN_PLACE = [
    "Ici c'est le séjour.",  # une pièce dite : notée (repère), jamais demandée (étape 13)
    "Ce mur donne dehors, brique 30 cm, isolé par l'intérieur, il y a deux fenêtres PVC double vitrage dessus.",
    "Volets roulants.",
    "Un mur donne sur le voisin.",
    "Pas d'autre mur.",
    "Au-dessus, des combles perdus isolés avec 30 cm de laine de verre.",
    "Terre-plein, pas isolé.",
    "Une chaudière gaz à condensation de 2015.",
    "Deux radiateurs à eau.",
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
    for numero, (phrase, cap, attendue) in enumerate(VISITE_PAR_COTES, 1):
        avant = len(recus)
        await phrase_filmee(session, phrase, cap, 10.0 * numero)
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
        conformes += questions == ([attendue] if attendue else [])
        claude = f" | Claude appelé : {_s(mesure.get('cerveau_total_s'))} s" if "cerveau_total_s" in mesure else ""
        print(f"{numero:2d}. « {phrase} »")
        print(f"    noté   : {', '.join(notes) or 'rien'}")
        print(f"    dit    : {' / '.join(questions) or '(rien)'}"
              f"{'' if questions == ([attendue] if attendue else []) else f'   ← attendu : {attendue or "(rien)"}'}")
        print(f"    temps  : extraction {mesure.get('extraction_ms')} ms | question {_s(mesure.get('question_s'))} s{claude}", flush=True)
    bilan = await session.terminer()

    def mediane(cle: str) -> str:
        valeurs = [m[cle] for m in session.mesures if isinstance(m.get(cle), (int, float))]
        return _s(statistics.median(valeurs)) if valeurs else "—"

    questions = [m["texte"] for m in recus if m["type"] == "dire"]
    reviennent = {"Des fenêtres ou une porte sur ce mur ?", "Ce mur donne sur quoi ?",
                  "D'autres fenêtres, ou une porte vers l'extérieur ?"}  # étape 13 : à chaque mur
    uniques = [q for q in questions if q not in reviennent]
    print("\nRésumé :")
    print(f"  questions conformes au parcours : {conformes}/{len(VISITE_PAR_COTES)} ; valeurs notées {bilan['acceptees']},"
          f" refusées {bilan['refusees']} ; DPE rempli à {round(100 * session.checklist.taux_dpe())} %")
    print(f"  questions avec « répét » / « pardon » : {sum(('répét' in q.lower()) or ('pardon' in q.lower()) for q in questions)}"
          f" ; questions doubles (2 « ? ») : {sum(q.count('?') > 1 for q in questions)}"
          f" ; même question reposée : {len(uniques) - len(set(uniques))} (hors celles qui reviennent à chaque mur ou pièce)")
    print(f"  Claude appelé pour {sum('cerveau_total_s' in m for m in session.mesures)} phrase(s) non comprise(s) sur {len(VISITE_PAR_COTES)},"
          f" et {bilan['relectures_claude']} relecture(s) en arrière-plan de phrases longues")
    print(f"  latence médiane : extraction {mediane('extraction_ms')} ms, question {mediane('question_s')} s")
    print("  + sur téléphone : ~0,7 s de silence de fin de phrase et ~2,3 s de transcription (mesurés à part)")
    return bilan


def main() -> None:
    parser = argparse.ArgumentParser(description="Évaluation de l'assistant sur une visite de deux pièces décrite par côté")
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
