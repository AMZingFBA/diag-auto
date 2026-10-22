"""Lancement : python -m assistant [--port 8443] [--sans-https]

En HTTPS par défaut, car un téléphone n'autorise la caméra et le micro que sur une page sécurisée.
Un certificat « auto-signé » est créé au premier lancement dans certificats/ : le téléphone
affichera un avertissement à accepter une fois (« Paramètres avancés » puis « Continuer »).
"""

from __future__ import annotations

import argparse
import datetime
import ipaddress
import logging
import socket

import uvicorn

from .reglages import DOSSIER_PROTOTYPE


def adresse_locale() -> str:
    """Adresse du PC sur le réseau local (aucun paquet n'est envoyé)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def certificat(adresse: str) -> tuple[str, str]:
    """Certificat auto-signé valable pour localhost et l'adresse locale (recréé si l'adresse change)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    dossier = DOSSIER_PROTOTYPE / "certificats"
    dossier.mkdir(exist_ok=True)
    cle_pem, cert_pem = dossier / "cle.pem", dossier / "certificat.pem"
    adresse_pem = cert_pem.with_suffix(".adresse")
    if cert_pem.exists() and adresse_pem.exists() and adresse_pem.read_text(encoding="utf-8") == adresse:
        return str(cle_pem), str(cert_pem)
    cle = ec.generate_private_key(ec.SECP256R1())
    nom = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DiagAuto prototype")])
    maintenant = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(nom).issuer_name(nom).public_key(cle.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - datetime.timedelta(days=1)).not_valid_after(maintenant + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.IPAddress(ipaddress.ip_address(adresse)),
        ]), critical=False)
        .sign(cle, hashes.SHA256())
    )
    cle_pem.write_bytes(cle.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    cert_pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    cert_pem.with_suffix(".adresse").write_text(adresse, encoding="utf-8")
    return str(cle_pem), str(cert_pem)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serveur du prototype d'assistant vocal DiagAuto (V1bis)")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--hote", default="0.0.0.0", help="0.0.0.0 = joignable depuis le téléphone sur le même Wi-Fi")
    parser.add_argument("--sans-https", action="store_true", help="HTTP simple (derrière un tunnel HTTPS, ou pour l'ordinateur seul)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")

    from .serveur import creer_app

    app = creer_app()
    statut = app.state.gestionnaire
    adresse = adresse_locale()
    options: dict = {}
    schema = "http"
    if not args.sans_https:
        cle, cert = certificat(adresse)
        options = {"ssl_keyfile": cle, "ssl_certfile": cert}
        schema = "https"
    print()
    print("  Assistant vocal DiagAuto — prototype V1bis")
    print(f"  Cerveau       : {statut.mode_cerveau}" + (f" ({statut.binaire_claude})" if statut.binaire_claude else ""))
    print(f"  Transcription : {statut.transcripteur.nom}")
    print(f"  Sur ce PC     : {schema}://localhost:{args.port}")
    print(f"  Sur le téléphone (même Wi-Fi) : {schema}://{adresse}:{args.port}")
    print()
    uvicorn.run(app, host=args.hote, port=args.port, log_level="warning", **options)


if __name__ == "__main__":
    main()
