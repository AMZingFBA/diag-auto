"""Faux Claude Code pour les tests : lit des messages stream-json, répond au fil de l'eau.

- message de préchauffage : {"dire": "", "actions": []}
- message contenant « LENT » : ne répond pas avant 5 s (test du délai)
- message contenant « PLANTE » : s'arrête
- sinon : une question et un enregistrement fixes, envoyés par petits morceaux.
"""

import json
import sys
import time

REPONSE = json.dumps({
    "dire": "Il est isolé ?",
    "actions": [{"outil": "enregistrer_reponse", "element_id": "", "type": "mur", "description": "le mur avec la télé",
                 "champ": "materiau", "valeur": "brique", "citation": "ce mur-là, brique"}],
}, ensure_ascii=False)


def ecrire(objet):
    sys.stdout.write(json.dumps(objet, ensure_ascii=False) + "\n")
    sys.stdout.flush()


ecrire({"type": "system", "subtype": "init", "model": "faux", "tools": []})
for ligne in sys.stdin:
    message = json.loads(ligne)["message"]
    textes = " ".join(b.get("text", "") for b in message["content"] if b.get("type") == "text")
    if "PLANTE" in textes:
        sys.stderr.write("arrêt demandé par le test\n")
        sys.exit(3)
    if "LENT" in textes:
        time.sleep(5)
    reponse = '{"dire": "", "actions": []}' if "Début de la visite" in textes else REPONSE
    for i in range(0, len(reponse), 7):
        ecrire({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": reponse[i:i + 7]}}})
    images = sum(1 for b in message["content"] if b.get("type") == "image")
    ecrire({"type": "result", "subtype": "success", "is_error": False, "num_turns": 1, "duration_api_ms": 10,
            "result": reponse, "total_cost_usd": 0.0001, "usage": {"input_tokens": 10 + images, "output_tokens": 5}})
