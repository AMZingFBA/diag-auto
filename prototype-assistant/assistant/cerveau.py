"""Le « cerveau » de l'assistant : Claude, appelé par le binaire Claude Code en mode headless.

Décision de Noah (22/10/2026) : pas de clé API Anthropic. Le serveur lance le Claude Code déjà
connecté sur ce PC (abonnement Claude Max) avec `claude -p` en entrée/sortie « stream-json »,
et garde ce processus ouvert pendant la visite. Mesures du 22/10/2026 (Haiku 5.5, effort bas) :
- relancer `claude -p` à chaque phrase : 2,7 à 6,3 s (démarrage ~1,3 s, et une étape de plus
  quand l'image est un fichier à lire avec l'outil Read) ;
- processus gardé ouvert, image dans le message : 1,8 à 2,0 s, premiers mots à ~1,3 s.
D'où le choix par défaut : processus persistant, images dans le message (`images="message"`).
Le mode `images="fichiers"` (images lues par l'outil Read) reste disponible pour comparer.

Claude ne peut pas écrire directement dans la checklist : il répond par un objet JSON
{"dire": ..., "actions": [...]} et c'est le serveur qui vérifie et applique chaque action.
"""

from __future__ import annotations

import asyncio
import base64
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from .checklist import TYPES, Checklist, horodatage

log = logging.getLogger(__name__)

SurDire = Callable[[str, str], Awaitable[None]]  # (question, code du champ visé)


@dataclass
class ImageInstant:
    t: float
    jpeg: bytes
    chemin: Path | None = None


@dataclass
class Contexte:
    mode: str  # « reponse » (le diagnostiqueur vient de parler) ou « veille » (il filme sans parler)
    t: float
    checklist: Checklist
    dialogue: list[str] = field(default_factory=list)
    images: list[ImageInstant] = field(default_factory=list)
    phrase: str = ""
    t_phrase: tuple[float, float] | None = None
    deja_note: list[str] = field(default_factory=list)  # noté par l'extraction immédiate à partir de cette phrase
    derniere_question: str = ""  # « M1.isolation : Il est isolé ? »
    questions_recentes: list[str] = field(default_factory=list)  # codes des champs déjà demandés récemment
    valeurs_attendues: list[str] = field(default_factory=list)  # réponses possibles à la dernière question
    autre_transcription: str = ""  # second avis de Whisper, quand il entend autre chose que le moteur rapide
    # Conversation (étape 7) : la question que le parcours propose, les remarques à dire, l'état de pause.
    suggestion: str = ""  # « « Ce mur est en quoi ? » [M2.materiau] »
    remarques: list[str] = field(default_factory=list)
    en_pause: bool = False
    # Étape 8 : ce que le serveur a déjà dit (« Noté. »), l'élément en cours de description, les murs montrés un par un.
    deja_dit: str = ""
    bip: bool = False  # étape 9 : le serveur a confirmé par un bip (pas de mots)
    en_cours: str = ""
    designations: list[str] = field(default_factory=list)


@dataclass
class Decision:
    dire: str = ""
    cible: str = ""  # code du champ visé par la question : « M1.isolation », « presence:fenetre »
    actions: list[dict] = field(default_factory=list)
    brut: str = ""
    erreur: str = ""
    mesures: dict = field(default_factory=dict)


# --- Consignes (fixes pendant toute la visite : elles restent en cache) ----------------------
# Étape 7 (Noah) : Claude est le cerveau de CHAQUE phrase. Il comprend tout et répond à tout (« c'est quoi un pont
# thermique ? », « on fait une pause », « tu as noté quoi pour la cuisine ? »), puis reprend la visite avec la question
# que le serveur lui propose. Les règles du serveur ne font que pré-remplir : elles ne le bloquent ni ne le contredisent.

CONSIGNES = """Tu es l'assistant vocal d'un diagnostiqueur immobilier, dans son oreillette, pendant qu'il filme un logement pour un DPE (méthode 3CL-2021). Tu parles avec lui comme un collègue compétent et sympathique : naturellement, brièvement, en français parlé, en le vouvoyant (comme les questions du parcours). Tu entends CHAQUE phrase qu'il dit (transcription automatique, souvent fautive) et tu vois les images qu'on t'envoie. Tu ne parles QUE de ce qui sert au DPE : murs, fenêtres et portes, plafonds, planchers, isolation, chauffage, eau chaude, ventilation. Le DPE décrit le logement entier : la pièce où il se trouve ne compte pas ; ne demande JAMAIS dans quelle pièce il est, ni quelle est la pièce suivante, et ne lui propose jamais de pièce. Tu ne décris jamais la décoration ni les objets (rideau, lampe, meuble, appareil) ; un objet ne sert qu'à nommer un mur ou une fenêtre (« le mur avec la télé »).

À chaque phrase :
1. Comprends-la librement, quelle qu'elle soit, comme dans une vraie conversation. Une transcription fautive s'interprète d'après la dernière question posée, ses valeurs possibles, le dialogue et les images (« Oh ! est chaude » à « à eau ou électrique ? » = eau chaude ; « parpin » = parpaing ; « ictérieur » = extérieur ; « cemur » = ce mur ; « murici » = mur ici ; « qui faut quoi doute ? » = il te faut quoi d'autre ?). Hésitations, répétitions, faux départs et débris sans sens (« Pourourir », « Djaddi ») ne comptent pas : ignore-les et comprends le reste ; une correction l'emporte (« alu, enfin bois » = bois).
2. Note TOUT ce qui sert au DPE, par des actions, avec ses mots en citation. Range chaque information sur le bon élément : une phrase qui ne nomme rien (« et l'isolant, c'est de la laine de verre 30 cm ») complète l'« Élément en cours de description » s'il est indiqué, même si la dernière question portait sur autre chose. Le serveur a déjà pré-rempli ce que ses règles ont reconnu (« Déjà noté automatiquement », éléments créés compris) : vérifie-le. S'il s'est trompé (valeur rangée sur le mauvais élément, mauvaise valeur), corrige par l'identifiant (enregistrer_reponse sur le bon element_id, et annuler le champ mal rangé) ; ne crée jamais un second élément pour la même chose ; ne renote pas ce qui est juste. Tu ne supprimes JAMAIS un élément de toi-même. Si tu doutes d'une interprétation, note quand même la plus probable avec certitude probable : le serveur la garde « à vérifier » pour l'écran de validation.
3. Réponds dans "dire", en commençant par une phrase très courte (quelques mots : la voix part dès qu'elle est écrite) :
   - à une question ou une remarque, quelle qu'elle soit (« c'est quoi un pont thermique ? », « comment ça va ? », « comment se construit une maison ? », « tu m'entends ? ») : réponds vraiment, en une à trois phrases courtes ; plus seulement s'il demande des détails ;
   - puis reprends la visite : termine par la « Question suivante du parcours » fournie par le serveur (elle porte sur ce qui manque vraiment pour le DPE ; c'est souvent la question restée sans réponse, à reposer). Si ta réponse a parlé d'autre chose, nomme l'élément dans la question, avec le nom donné entre « » (« Et le mur sud, il est en quoi ? ») ;
   - à une simple réponse ou une description (« brique », « oui, deux », « l'isolant c'est de la laine de verre 30 cm ») : ne répète RIEN de ce qu'il vient de dire (ni la valeur, ni « c'est noté », ni une reformulation : le serveur a déjà confirmé par un bip), pose directement la question suivante ;
   - récapitule seulement s'il le demande, ou quand la pièce est terminée (une phrase) ;
   - une seule question par réponse, toujours à la fin ; "cible" = son code (celui de la question suivante si c'est elle) ;
   - « Déjà dit par le serveur à l'instant » (« Noté. », « Alors… ») : ne le répète pas, enchaîne directement.
4. Ordres et demandes :
   - « on fait une pause », « je prends un appel » : action pause, réponds brièvement, plus aucune question du parcours jusqu'à « on reprend » (action reprendre, puis question suivante) ;
   - « on passe à la cuisine », « là c'est la chambre » : action piece_courante (avec sa citation), un simple repère qui ne change rien au DPE ; enchaîne avec la question suivante proposée. Une pièce vue sur les images seulement : aucune action, rien à dire ;
   - nom de pièce dit : un vrai nom (« Séjour », « Cuisine », « Chambre 1 ») ; « la première pièce » sans autre nom : « Pièce 1 » ;
   - ne pose jamais toi-même « un autre mur ? », « quels murs dans cette pièce ? » ni « d'autres fenêtres ? » : le serveur pose « ce mur donne sur quoi ? », puis demande les côtés qui manquent un par un (« Et le mur sud, il donne sur quoi ? ») et « Un autre mur autour du logement, à me montrer ? » ;
   - une réponse peut arriver cochée sur le téléphone (« Diagnostiqueur (coché sur le téléphone) » dans le dialogue) : elle vaut une réponse dite, déjà notée ; ne la redemande pas ;
   - « ce mur, ce mur et ce mur » : le serveur a créé un mur par « ce mur », avec l'image de son instant (« Murs montrés un par un ») ; donne à chacun un repère visuel tiré de son image (signaler_element avec son element_id et "repere" : « avec le tableau »), puis pose la question suivante ; ne demande pas « un autre mur ? » ;
   - « tu as noté quoi pour la cuisine ? », « où on en est ? » : récapitule d'après l'état fourni, en deux ou trois phrases (l'essentiel, puis ce qui manque) ;
   - « quel mur ? », « il te faut quoi ? » : explique avec les noms de l'état (« le mur côté voisin, celui affiché à l'écran »), puis repose la question ;
   - « oublie ce que je viens de dire sur la fenêtre », « annule ça » : action annuler sur ce qu'il désigne (avec champ : la valeur revient à la précédente ; sans champ : l'élément est retiré). annuler ne sert qu'à cela, et à corriger un pré-remplissage faux de cette phrase ; une correction ordinaire (« non, c'est du parpaing ») est un enregistrer_reponse.
5. « Remarques du serveur » : dis-les brièvement avant ta question (contradiction relevée, valeur invraisemblable à faire confirmer, boussole à calibrer).

Règles absolues :
- Tu n'inventes JAMAIS une donnée du logement : une valeur n'est notée que si le diagnostiqueur l'a dite (citation = ses mots tels que transcrits). Une image ne suffit pas pour une valeur ; elle sert à signaler un élément ou à le désigner.
- Questions générales ou techniques : réponds juste et simplement ; si tu n'es pas sûr, dis-le.
- Ne fais JAMAIS répéter : jamais « pardon », « répétez », « pas compris ». Ne demande confirmation que si deux lectures très différentes sont possibles (« J'ai compris brique, c'est bien ça ? »).
- « Je ne sais pas » : valeur « inconnu » pour le champ demandé, puis question suivante.
- Ne dis jamais qu'un élément est « déjà noté » ou « un doublon » sans preuve dans l'état : même repère, même orientation ou même description. Dans le doute, c'est un nouvel élément ; si tu penses qu'il est peut-être en double, action doublon (le serveur lui demande « C'est le même mur que… ? ») et ne pose pas d'autre question ; ne le supprime jamais toi-même.
- Plusieurs éléments identiques montrés un par un (« une fenêtre ici, une fenêtre ici, une fenêtre là-bas ») : un seul élément avec son nombre (compter), pas plusieurs éléments.
- Ne demande jamais une information déjà dite : ni un champ renseigné, ni une question de la liste « Déjà demandé », ni ce qu'il vient de dire dans le dialogue récent (même mal rangé : range-le au lieu de le redemander). Pas de question absurde (une fenêtre n'a pas d'épaisseur).
- Ne dis jamais « le mur 3 », « le quatrième mur » ni aucun numéro : désigne un élément par son nom entre « » dans l'état (« le mur nord, celui avec la télé ») ou par « ce mur » s'il vient d'en parler. Dans les actions, utilise toujours l'identifiant (M3).
- "dire" est lu à voix haute : phrases courtes, pas de liste, pas de symbole, pas de markdown, pas d'émoji.
- Phrase adressée à quelqu'un d'autre (« allô ») : aucune action, "dire" vide. Phrase qui n'est que débris (bruit mal transcrit) : aucune action ; "dire" vide, ou la question en attente reposée telle quelle.

Enveloppe (le DPE décrit ce qui entoure le logement, pas chaque pièce) : les murs, le plafond et le plancher sont ceux du LOGEMENT. Un mur se reconnaît à son côté (nord, est, sud, ouest) : « le mur ouest », ce sont tous les murs ouest du logement, toutes pièces confondues. Un mur filmé dans une autre pièce, du même côté qu'un mur déjà décrit, est ce mur-là : le serveur l'y rattache, ne le redécris pas et ne le redemande pas. Un mur entre deux pièces du logement (« donne sur la cuisine », « c'est une cloison ») est hors de l'enveloppe : note donne_sur « local chauffé » et rien d'autre, ne pose aucune question dessus. Un voisin (« local chauffé (voisin) ») est bien un côté du logement. « Au nord le voisin, au sud la cour » : un mur par côté (signaler_element, orienter, enregistrer_reponse). Un même mur peut avoir plusieurs parties : « mur est : 60 % sur le voisin, 40 % dehors » = la première partie sur le mur (donne_sur, part « 60 % »), puis scinder pour l'autre (valeurs donne_sur et part « 40 % ») ; une valeur dite autrement dans une autre pièce (côté séjour sur la rue, côté chambre sur le voisin) est une autre partie : le serveur la crée. Les fenêtres et les portes sont sur leur mur (signaler_element avec "support" : l'identifiant du mur), sur la partie qui donne dehors ; le serveur demande « des fenêtres ou une porte sur ce mur ? » mur par mur. Les radiateurs sont ceux du logement : leur type compte, pas leur nombre par pièce. Le plafond et le plancher du logement se décrivent une fois ; s'il dit qu'ils sont différents à un endroit (« ici le plancher est sur terre-plein »), c'en est une autre partie.

Description libre : une phrase peut décrire plusieurs éléments d'un coup ; note tout en une fois (un élément avec "nombre" pour des éléments identiques). Ne suppose jamais que tout est identique : « 9 radiateurs électriques basse température et 1 électrique haute température » = deux éléments distincts. Exception dans un groupe (« dont une en bois », « tous sauf un ») : scinder puis compter. « Toutes les fenêtres sont en bois sauf celle de la chambre » : regle. « Tous les murs de la maison sont en brique » : regle (type mur, piece vide) : elle vaut pour tous les murs, déjà décrits et à venir ; ne demande plus jamais leur matériau. « Le reste donne sur l'intérieur ou les voisins » : donne_sur pour les murs sans valeur, puis cloturer mur. Un mur sur un local chauffé n'a besoin de rien d'autre. Date et température des radiateurs : ne les demande jamais, note-les si elles sont dites. Orientation (nord, sud, est, ouest) : la boussole la donne ; si elle est dite ou corrigée (« non, c'est le mur ouest »), action orienter. Une valeur invraisemblable (un mur de 30 m de long) est contrôlée par le serveur.

L'état de la checklist (calculé par le serveur, source de vérité) est donné à chaque message : pièce courante en détail, autres pièces, enveloppe du logement par côté, équipements, règles. Le plafond et le plancher du logement existent toujours.

Deux sortes de messages :
- « reponse » : le diagnostiqueur vient de parler. Sa phrase, la dernière question posée, ce qui est déjà noté et la question suivante du parcours sont fournis.
- « veille » : il filme sans parler. Signale seulement les éléments nouveaux bien visibles (fenêtre, radiateur, chaudière, ballon, bouche de VMC) ; "dire" vide. Jamais de pièce devinée sur les images.

Format de réponse : UNIQUEMENT un objet JSON sur une ligne, sans texte autour, dans cet ordre (le serveur lit "dire" à voix haute pendant que tu l'écris, phrase par phrase) :
{"cible": "<code de ta question, vide si aucune>", "dire": "<ce que tu dis>", "actions": [<actions>]}

Actions possibles :
{"outil": "piece_courante", "nom": "Chambre 1", "citation": "<mots dits, ou vide si tu le déduis de l'image>"}
{"outil": "signaler_element", "type": "<type>", "description": "<courte, avec article : le mur avec la télé>", "nombre": 1, "support": "<fenêtre ou porte : l'identifiant du mur qui la porte>"}
{"outil": "enregistrer_reponse", "element_id": "<M1… si l'élément existe, sinon vide>", "type": "<type>", "description": "<pour un nouvel élément>", "nombre": 1, "champ": "<champ>", "valeur": "<valeur courte>", "citation": "<mots dits>", "certitude": "<sur ou probable>"}
{"outil": "marquer_sans_objet", "element_id": "<id ou vide>", "type": "<type>", "champ": "<champ, ou presence pour « pas de fenêtre ici »>", "citation": "<mots dits>"}
{"outil": "annuler", "element_id": "<id>", "champ": "<champ pré-rempli à tort dans cette phrase ; ou, seulement s'il le demande (« oublie… »), le champ à oublier, ou vide pour retirer l'élément>"}
{"outil": "doublon", "element_id": "<élément peut-être en double>", "meme_que": "<l'autre élément>", "preuve": "<même repère, même orientation ou même description, d'après l'état ; ou vide>"}
{"outil": "cloturer", "type": "<mur ou fenetre>", "citation": "<mots dits : « pas d'autre mur »>"}
{"outil": "copier", "type": "<plafond ou plancher>", "piece_source": "<nom de la pièce>", "citation": "<mots dits : « pareil que le séjour », quand cette pièce avait sa propre partie>"}
{"outil": "scinder", "element_id": "<groupe existant, ou mur à partager>", "nombre": 1, "description": "<nom parlant : la fenêtre en bois>", "valeurs": {"<champ>": "<valeur dite pour cette partie>"}, "citation": "<mots dits>"}
{"outil": "compter", "element_id": "<id>", "nombre": 2, "description": "<nouveau nom, ou vide>", "correction": <true si un nombre déjà dit est corrigé>, "citation": "<mots dits>"}
{"outil": "regle", "type": "<type>", "valeurs": {"<champ>": "<valeur>"}, "piece": "<vide = tout le logement, ou nom de la pièce>", "exceptions": {"<pièce exceptée>": {"<champ>": "<valeur>"}}, "citation": "<mots dits>"}
{"outil": "orienter", "element_id": "<M1, F2…>", "orientation": "<nord, sud, est ou ouest>", "citation": "<mots dits>"}
{"outil": "pause"}
{"outil": "reprendre"}
Un élément d'une autre pièce que la pièce courante : ajoute "piece": "<nom de la pièce>" à signaler_element ou enregistrer_reponse (pour un mur, la pièce où il est vu).

Types (niveau) et champs (entre crochets : facultatif, à noter s'il est dit, jamais à demander) :
{champs}

Exemples de valeurs courtes : matériau « brique », « parpaing », « béton », « pierre », « bois », « plâtre » ; épaisseur « 30 cm » ; isolation « non isolé », « ITI laine de verre 10 cm », « ITE », « inconnu » ; donne sur « extérieur », « local non chauffé : garage », « local chauffé (voisin) », « local chauffé » (une autre pièce du logement) ; longueur « 4,50 m » ; part « 60 % » ; menuiserie « PVC », « bois », « alu » ; vitrage « double » ; volets « roulants », « aucun » ; émetteur « radiateur à eau », « convecteur électrique » ; température « basse ».

Exemples.
Phrase « c'est quoi un pont thermique ? » (question suivante du parcours : « Ce mur est isolé ? » [M2.isolation]) →
{"cible": "M2.isolation", "dire": "C'est un endroit où la chaleur s'échappe plus vite, souvent à la jonction entre un mur et un plancher, ou autour des fenêtres. Et ce mur, il est isolé ?", "actions": []}
Phrase « on fait une pause, je prends un appel » →
{"cible": "", "dire": "D'accord, je vous attends.", "actions": [{"outil": "pause"}]}
Phrase « l'isolant, c'est de la laine de verre 30 cm » (déjà noté automatiquement : M1.isolation = isolé laine de verre 30 cm ; le serveur a confirmé par un bip ; question suivante : « Il est en quoi ? » [M1.materiau]) →
{"cible": "M1.materiau", "dire": "Il est en quoi ?", "actions": []}
Phrase « le radiateur de la chambre est électrique, un vieux grille-pain » (déjà noté automatiquement : nouvel élément E2 (« le radiateur électrique », pièce Chambre), E2.type = radiateur électrique ; question suivante : « Sous le logement : terre-plein, vide sanitaire, cave ou un autre logement ? » [PB1.donne_sur]) →
{"cible": "PB1.donne_sur", "dire": "Sous le logement : terre-plein, vide sanitaire, cave ou un autre logement ?", "actions": [{"outil": "enregistrer_reponse", "element_id": "E2", "type": "emetteur", "champ": "type", "valeur": "convecteur électrique", "citation": "un vieux grille-pain", "certitude": "sur"}]}
Phrase « le mur est, 60 % sur le voisin et 40 % sur la rue » (déjà noté automatiquement : M4.donne_sur = local chauffé (voisin), M4.part = 60 %, scinder M4 → M5 donne_sur = extérieur, part = 40 % ; question suivante : « Le mur est côté rue est en quoi ? » [M5.materiau]) →
{"cible": "M5.materiau", "dire": "Le mur est côté rue est en quoi ?", "actions": []}
Phrase « ce mur fait 4 m 50 de long, brique 30 cm, isolé par l'intérieur, il y a trois fenêtres en bois double vitrage » (déjà noté automatiquement : M1.longueur, M1.materiau, M1.epaisseur, M1.isolation, F1 ×3 menuiserie et vitrage ; question suivante : « Ce mur donne sur quoi ? » [M1.donne_sur]) →
{"cible": "M1.donne_sur", "dire": "Ce mur donne sur quoi ?", "actions": []}"""


def consignes() -> str:
    lignes = []
    for t in TYPES.values():
        niveau = ("logement, par côté" if t.cle == "mur" else "logement, sur son mur" if t.cle in ("fenetre", "porte")
                  else "pièce" if t.niveau == "piece" else "logement")
        champs = ", ".join(f"{c.cle} = {c.libelle}" if c.obligatoire else f"[{c.cle} = {c.libelle}]" for c in t.champs)
        lignes.append(f"- {t.cle} ({t.nom}, {niveau}) : {champs}")
    return CONSIGNES.replace("{champs}", "\n".join(lignes))


def texte_message(contexte: Contexte, chemins_images: list[Path] | None = None) -> str:
    lignes = [f"[{contexte.mode}] Instant : {horodatage(contexte.t)}"]
    if chemins_images:
        lignes.append("Images de l'instant, à lire avec l'outil Read (la dernière = maintenant) : " + ", ".join(str(c) for c in chemins_images))
    elif contexte.images:
        lignes.append("Images jointes : " + ", ".join(horodatage(i.t) for i in contexte.images) + " (la dernière = maintenant)")
    else:
        lignes.append("Pas d'image (réseau ou caméra).")
    lignes += ["", "État de la checklist (calculé par le serveur) :", contexte.checklist.resume_pour_ia(), ""]
    lignes += ["Dialogue récent :", *(contexte.dialogue or ["(rien)"]), ""]
    lignes.append("Déjà demandé récemment (ne pas redemander) : " + (", ".join(contexte.questions_recentes) or "rien"))
    if contexte.mode in ("reponse", "complement"):
        debut, fin = contexte.t_phrase or (contexte.t, contexte.t)
        lignes.append(f"Dernière question posée : {contexte.derniere_question or 'aucune'}")
        if contexte.valeurs_attendues:
            lignes.append("Valeurs possibles pour cette question : " + ", ".join(contexte.valeurs_attendues))
        lignes.append("Déjà noté automatiquement à partir de cette phrase : " + ("; ".join(contexte.deja_note) or "rien"))
        if contexte.designations:
            lignes.append("Murs montrés un par un (créés par le serveur, images jointes dans l'ordre) : " + "; ".join(contexte.designations))
        if contexte.en_cours:
            lignes.append(f"Élément en cours de description : {contexte.en_cours} (une phrase qui ne nomme rien le complète)")
        if contexte.deja_dit:
            lignes.append(f"Déjà dit par le serveur à l'instant : « {contexte.deja_dit} » (ne le répète pas, enchaîne)")
        if contexte.bip:
            lignes.append("Le serveur a déjà confirmé par un bip : ne dis rien de ce qu'il vient de dire, pose directement la question.")
        if contexte.en_pause:
            lignes.append("Visite EN PAUSE : ne pose aucune question du parcours ; réponds seulement, jusqu'à « on reprend ».")
        if contexte.suggestion:
            lignes.append(f"Question suivante du parcours (à poser à la fin de ta réponse, reformulée si besoin) : {contexte.suggestion}")
        if contexte.remarques:
            lignes.append("Remarques du serveur (à dire brièvement) : " + " ".join(contexte.remarques))
        lignes.append(f"Nouvelle phrase du diagnostiqueur [{horodatage(debut)}–{horodatage(fin)}] : « {contexte.phrase} »")
        if contexte.autre_transcription:
            lignes.append(f"Autre transcription possible de la même phrase : « {contexte.autre_transcription} »")
    else:
        lignes.append("Veille : pas de nouvelle phrase. Que faut-il signaler ?")
    return "\n".join(lignes)


def contenu_message(contexte: Contexte, images: str) -> list[dict]:
    """Contenu du message utilisateur au format de l'API Messages (texte + images)."""
    if images == "fichiers":
        chemins = [i.chemin for i in contexte.images if i.chemin]
        return [{"type": "text", "text": texte_message(contexte, chemins)}]
    contenu: list[dict] = []
    for image in contexte.images:
        contenu.append({"type": "text", "text": f"Image à {horodatage(image.t)}"})
        contenu.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(image.jpeg).decode()},
        })
    contenu.append({"type": "text", "text": texte_message(contexte)})
    return contenu


def _champ_json(nom: str) -> re.Pattern:
    return re.compile(rf'"{nom}"\s*:\s*"((?:[^"\\]|\\.)*)"')


_DIRE, _CIBLE = _champ_json("dire"), _champ_json("cible")


def _lire_champ(motif: re.Pattern, texte: str) -> str | None:
    m = motif.search(texte)
    if not m:
        return None
    try:
        return json.loads(f'"{m.group(1)}"')
    except json.JSONDecodeError:
        return None


_DEBUT_DIRE = re.compile(r'"dire"\s*:\s*"')
_FIN_DE_PHRASE = re.compile(r"(?<=[.!?…])\s+")


def dire_partiel(texte_partiel: str) -> tuple[str, bool]:
    """Ce qui est déjà arrivé du champ « dire » (même inachevé), et s'il est complet : la voix démarre dès la
    première phrase, sans attendre la fin de la réponse de Claude (étape 7)."""
    m = _DEBUT_DIRE.search(texte_partiel)
    if not m:
        return "", False
    i, brut = m.end(), []
    while i < len(texte_partiel):
        c = texte_partiel[i]
        if c == "\\":
            longueur = 6 if texte_partiel[i + 1:i + 2] == "u" else 2
            if i + longueur > len(texte_partiel):
                break  # échappement pas encore arrivé en entier
            brut.append(texte_partiel[i:i + longueur])
            i += longueur
            continue
        if c == '"':
            return json.loads('"' + "".join(brut) + '"'), True
        brut.append(c)
        i += 1
    try:
        return json.loads('"' + "".join(brut) + '"'), False
    except json.JSONDecodeError:
        return "", False


def phrases_finies(texte: str, complet: bool = True) -> list[str]:
    """Les phrases terminées du texte (toutes s'il est complet ; sinon la dernière, inachevée, attend)."""
    phrases = [p.strip() for p in _FIN_DE_PHRASE.split(texte) if p.strip()]
    return phrases if complet else phrases[:-1]


def extraire_dire(texte_partiel: str) -> str | None:
    """Le champ « dire » dès qu'il est complet dans le texte en cours d'arrivée."""
    return _lire_champ(_DIRE, texte_partiel)


def extraire_cible(texte_partiel: str) -> str:
    return _lire_champ(_CIBLE, texte_partiel) or ""


def analyser_reponse(texte: str) -> Decision:
    """Lit l'objet JSON renvoyé par Claude (tolère des balises ``` ou du texte autour)."""
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut < 0 or fin <= debut:
        return Decision(brut=texte, erreur="réponse sans objet JSON")
    try:
        donnees = json.loads(texte[debut : fin + 1])
    except json.JSONDecodeError as e:
        return Decision(dire=extraire_dire(texte) or "", cible=extraire_cible(texte), brut=texte, erreur=f"JSON invalide : {e}")
    if not isinstance(donnees, dict):
        return Decision(brut=texte, erreur="la réponse n'est pas un objet JSON")
    dire = donnees.get("dire") if isinstance(donnees.get("dire"), str) else ""
    cible = donnees.get("cible") if isinstance(donnees.get("cible"), str) else ""
    actions = [a for a in donnees.get("actions") or [] if isinstance(a, dict)]
    return Decision(dire=dire.strip(), cible=cible.strip(), actions=actions, brut=texte)


# --- Lancement de Claude Code ----------------------------------------------------------------


def trouver_claude() -> str | None:
    """Chemin du binaire Claude Code : DIAGAUTO_CLAUDE, sinon `claude` dans le PATH, sinon celui
    installé avec l'extension VS Code (le plus récent), sinon l'installation native."""
    if os.environ.get("DIAGAUTO_CLAUDE"):
        return os.environ["DIAGAUTO_CLAUDE"]
    if trouve := shutil.which("claude"):
        return trouve
    accueil = Path.home()
    candidats = []
    for motif in (".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude*",
                  ".vscode-insiders/extensions/anthropic.claude-code-*/resources/native-binary/claude*"):
        candidats += [Path(c) for c in glob.glob(str(accueil / motif)) if Path(c).name in ("claude", "claude.exe")]

    def version(chemin: Path) -> tuple[int, ...]:
        m = re.search(r"claude-code-(\d+)\.(\d+)\.(\d+)", str(chemin))
        return tuple(int(x) for x in m.groups()) if m else (0,)

    if candidats:
        return str(max(candidats, key=version))
    for natif in (accueil / ".local/bin/claude.exe", accueil / ".local/bin/claude"):
        if natif.exists():
            return str(natif)
    return None


# Variables retirées de l'environnement de Claude Code :
# - une clé API ferait payer l'API au lieu d'utiliser l'abonnement (décision de Noah : pas de clé) ;
# - celles d'une session Claude Code parente (quand le serveur est lancé depuis Claude Code).
_RETIRER = {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE", "CLAUDE_PID", "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_EFFORT"}


def env_claude() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _RETIRER and not k.startswith("CLAUDE_CODE_")}


def commande_claude(binaire: str, modele: str, effort: str, images: str) -> list[str]:
    outils = ["--tools", "Read", "--allowedTools", "Read"] if images == "fichiers" else ["--tools", ""]
    return [
        binaire, "-p",
        "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        "--model", modele, "--effort", effort,
        "--safe-mode",  # ignore CLAUDE.md, hooks, extensions et MCP personnels ; garde la connexion
        "--no-session-persistence",  # rien n'est gardé dans l'historique de Claude Code
        "--permission-prompts", "none",  # personne pour répondre : tout ce qui demanderait est refusé
        "--system-prompt", consignes(),
        *outils,
    ]


class ProcessusClaude:
    """Un processus Claude Code ouvert : on lui écrit des messages, il répond au fil de l'eau."""

    def __init__(self, commande: list[str], dossier: Path) -> None:
        self.commande = commande
        self.dossier = dossier
        self.tours = 0
        self.erreurs: list[str] = []
        self._p: subprocess.Popen | None = None
        self._file: asyncio.Queue | None = None
        self._verrou = asyncio.Lock()

    @property
    def vivant(self) -> bool:
        return self._p is not None and self._p.poll() is None

    async def demarrer(self) -> None:
        boucle = asyncio.get_running_loop()
        self._file = asyncio.Queue()
        self.dossier.mkdir(parents=True, exist_ok=True)
        self._p = subprocess.Popen(
            self.commande, cwd=self.dossier, env=env_claude(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._lire, args=(boucle,), daemon=True).start()
        threading.Thread(target=self._lire_erreurs, daemon=True).start()

    def _lire(self, boucle: asyncio.AbstractEventLoop) -> None:
        assert self._p and self._p.stdout and self._file
        try:
            for ligne in self._p.stdout:
                try:
                    evenement = json.loads(ligne.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                boucle.call_soon_threadsafe(self._file.put_nowait, evenement)
            boucle.call_soon_threadsafe(self._file.put_nowait, None)  # fin du processus
        except RuntimeError:
            pass  # la visite est terminée (boucle fermée) : plus personne n'attend ces messages

    def _lire_erreurs(self) -> None:
        assert self._p and self._p.stderr
        for ligne in self._p.stderr:
            texte = ligne.decode("utf-8", "replace").strip()
            if texte:
                self.erreurs = (self.erreurs + [texte])[-20:]

    def _ecrire(self, donnees: bytes) -> None:
        assert self._p and self._p.stdin
        self._p.stdin.write(donnees)
        self._p.stdin.flush()

    async def demander(self, contenu: list[dict], sur_texte: Callable[[str], Awaitable[None]] | None, delai_s: float) -> tuple[str, dict, dict]:
        """Envoie un message ; renvoie (texte complet, événement « result », mesures)."""
        async with self._verrou:
            if not self.vivant or self._file is None:
                raise RuntimeError("Claude Code n'est pas lancé : " + " | ".join(self.erreurs[-3:]))
            ligne = json.dumps({"type": "user", "message": {"role": "user", "content": contenu}}, ensure_ascii=False) + "\n"
            debut = time.perf_counter()
            await asyncio.to_thread(self._ecrire, ligne.encode("utf-8"))
            self.tours += 1
            texte, premier_mot, reflexion = "", None, False
            while True:
                restant = delai_s - (time.perf_counter() - debut)
                try:
                    evenement = await asyncio.wait_for(self._file.get(), max(restant, 0.01))
                except asyncio.TimeoutError:
                    self.arreter()
                    raise TimeoutError(f"pas de réponse de Claude en {delai_s:.0f} s") from None
                if evenement is None:
                    raise RuntimeError("Claude Code s'est arrêté : " + " | ".join(self.erreurs[-3:]))
                if evenement.get("type") == "stream_event":
                    e = evenement.get("event", {})
                    if e.get("type") == "content_block_start" and e.get("content_block", {}).get("type") == "thinking":
                        reflexion = True
                    if e.get("type") == "content_block_delta" and e.get("delta", {}).get("type") == "text_delta":
                        if premier_mot is None:
                            premier_mot = time.perf_counter() - debut
                        texte += e["delta"]["text"]
                        if sur_texte:
                            await sur_texte(texte)
                elif evenement.get("type") == "result":
                    usage = evenement.get("usage") or {}
                    mesures = {
                        "premier_mot_s": round(premier_mot, 3) if premier_mot is not None else None,
                        "total_s": round(time.perf_counter() - debut, 3),
                        "api_cumule_s": round((evenement.get("duration_api_ms") or 0) / 1000, 3),  # depuis le lancement du processus
                        "etapes": evenement.get("num_turns"),
                        # Claude Code fait toujours réfléchir Haiku 5.5 avant de répondre (mesuré le 22/10/2026 :
                        # ni alwaysThinkingEnabled=false, ni MAX_THINKING_TOKENS=0 ne l'empêchent).
                        "reflexion": reflexion,
                        "jetons_entree": usage.get("input_tokens"),
                        "jetons_cache_lus": usage.get("cache_read_input_tokens"),
                        "jetons_cache_ecrits": usage.get("cache_creation_input_tokens"),
                        "jetons_sortie": usage.get("output_tokens"),
                        # Estimation fournie par Claude Code au tarif API : non facturée avec l'abonnement.
                        "cout_equivalent_api_usd": evenement.get("total_cost_usd"),
                    }
                    if evenement.get("is_error"):
                        raise RuntimeError(f"erreur Claude Code : {evenement.get('result') or evenement.get('subtype')}")
                    return (evenement.get("result") or texte), evenement, mesures

    def arreter(self) -> None:
        if self._p and self._p.poll() is None:
            try:
                if self._p.stdin:
                    self._p.stdin.close()
                self._p.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                self._p.kill()


MESSAGE_PRECHAUFFAGE = "Début de la visite : rien n'est encore filmé. Réponds exactement {\"dire\": \"\", \"actions\": []}"


class CerveauClaudeCode:
    """Claude via Claude Code (abonnement). Un processus ouvert, remplacé tous les `tours_max`
    messages par un processus neuf préparé à l'avance (la conversation ne grossit pas sans fin ;
    l'état utile est de toute façon renvoyé à chaque message)."""

    def __init__(self, dossier: Path, modele: str = "claude-haiku-5-5", effort: str = "low", images: str = "message",
                 tours_max: int = 12, delai_s: float = 25.0, binaire: str | None = None, commande: list[str] | None = None) -> None:
        self.dossier = dossier
        self.modele = modele
        self.images = images
        self.tours_max = tours_max
        self.delai_s = delai_s
        if commande is None:
            binaire = binaire or trouver_claude()
            if not binaire:
                raise FileNotFoundError("Claude Code introuvable : installez-le ou indiquez son chemin dans DIAGAUTO_CLAUDE")
            commande = commande_claude(binaire, modele, effort, images)
        self.commande = commande
        self._actuel: ProcessusClaude | None = None
        self._suivant: asyncio.Task | None = None
        self.prechauffage: dict = {}

    @property
    def nom(self) -> str:
        return f"Claude Code (abonnement), modèle {self.modele}, images {'dans le message' if self.images == 'message' else 'en fichiers'}"

    async def _nouveau_processus(self) -> ProcessusClaude:
        processus = ProcessusClaude(self.commande, self.dossier)
        await processus.demarrer()
        _, _, mesures = await processus.demander([{"type": "text", "text": MESSAGE_PRECHAUFFAGE}], None, self.delai_s * 2)
        self.prechauffage = mesures
        return processus

    async def demarrer(self) -> None:
        self._actuel = await self._nouveau_processus()

    async def _processus(self) -> ProcessusClaude:
        if self._actuel is None or not self._actuel.vivant:
            self._actuel = await self._nouveau_processus()
        if self._actuel.tours >= self.tours_max - 5 and self._suivant is None:
            self._suivant = asyncio.create_task(self._nouveau_processus())
        if self._actuel.tours >= self.tours_max and self._suivant is not None and self._suivant.done():
            tache, self._suivant = self._suivant, None
            if tache.exception() is None:
                ancien, self._actuel = self._actuel, tache.result()
                asyncio.get_running_loop().run_in_executor(None, ancien.arreter)
            else:
                log.warning("Processus Claude de relève en échec : %s", tache.exception())
        return self._actuel

    async def decider(self, contexte: Contexte, sur_dire: SurDire | None = None) -> Decision:
        """Envoie le contexte à Claude. `sur_dire` reçoit « dire » phrase par phrase, dès que chacune est écrite."""
        emises = 0
        debut = time.perf_counter()
        premiere_phrase: float | None = None

        async def sur_texte(texte_partiel: str) -> None:
            nonlocal emises, premiere_phrase
            if sur_dire is None:
                return
            dire, complet = dire_partiel(texte_partiel)
            for phrase in phrases_finies(dire, complet)[emises:]:
                emises += 1
                if premiere_phrase is None:
                    premiere_phrase = time.perf_counter() - debut
                await sur_dire(phrase, extraire_cible(texte_partiel))

        try:
            processus = await self._processus()
            texte, _, mesures = await processus.demander(contenu_message(contexte, self.images), sur_texte, self.delai_s)
        except (RuntimeError, TimeoutError, OSError) as e:
            log.warning("Cerveau Claude : %s", e)
            return Decision(erreur=str(e))
        decision = analyser_reponse(texte)
        mesures["premiere_phrase_s"] = round(premiere_phrase, 3) if premiere_phrase is not None else None
        decision.mesures = mesures
        if sur_dire:  # ce qui n'a pas pu être lu au fil de l'eau (JSON mal formé, réponse d'un bloc)
            for phrase in phrases_finies(decision.dire)[emises:]:
                await sur_dire(phrase, decision.cible)
        return decision

    async def fermer(self) -> None:
        if self._suivant:
            self._suivant.cancel()
        if self._actuel:
            self._actuel.arreter()
