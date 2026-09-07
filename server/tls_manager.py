import os
import socket
import datetime
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import ipaddress

BASE_DIR = Path(__file__).resolve().parent.parent
CERTS_DIR = Path(os.getenv("CERTS_DIR", str(BASE_DIR / "certs")))
CERTS_DIR.mkdir(parents=True, exist_ok=True)
try:
    os.chmod(str(CERTS_DIR), 0o777)
except Exception:
    pass
CERT_PATH = CERTS_DIR / "cert.pem"
KEY_PATH = CERTS_DIR / "key.pem"


def get_local_ips():
    ips = {"127.0.0.1"}
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ":" not in ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    return list(ips)

def ensure_tls_certificates():
    """Generates self-signed TLS certificates if none exist."""
    if CERT_PATH.exists() and KEY_PATH.exists():
        return str(CERT_PATH), str(KEY_PATH)

    print("[TLS] Generating self-signed TLS certificate for HTTPS...")
    
    # 1. Generate Private Key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # 2. Setup Subject and Alternative Names (SAN)
    hostname = socket.gethostname()
    local_ips = get_local_ips()

    san_list = [
        x509.DNSName("localhost"),
        x509.DNSName(hostname),
    ]
    for ip_str in local_ips:
        try:
            san_list.append(x509.IPAddress(ipaddress.ip_address(ip_str)))
        except ValueError:
            pass

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BlockyDNS Hub"),
        x509.NameAttribute(NameOID.COMMON_NAME, "BlockyDNS Local Gateway"),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650)) # 10 years validity
        .add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )

    # 3. Write files
    with open(KEY_PATH, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    with open(CERT_PATH, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    try:
        os.chmod(str(KEY_PATH), 0o666)
        os.chmod(str(CERT_PATH), 0o666)
        os.chmod(str(CERTS_DIR), 0o777)
    except Exception:
        pass

    print(f"[TLS] Successfully generated certificate at {CERT_PATH} with SANs: {[s.value for s in san_list]}")
    return str(CERT_PATH), str(KEY_PATH)


def get_certificate_info():
    """Returns details about the active certificate."""
    if not CERT_PATH.exists():
        return {"active": False, "status": "No certificate found"}
    try:
        with open(CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        
        sans = []
        try:
            ext = cert.extensions.get_extension_for_oid(x509.OID_SUBJECT_ALTERNATIVE_NAME)
            sans = [str(name.value) for name in ext.value]
        except Exception:
            pass

        return {
            "active": True,
            "issuer": cert.issuer.rfc4514_string(),
            "subject": cert.subject.rfc4514_string(),
            "valid_from": cert.not_valid_before_utc.isoformat(),
            "valid_to": cert.not_valid_after_utc.isoformat(),
            "sans": sans,
            "is_self_signed": cert.issuer == cert.subject
        }
    except Exception as e:
        return {"active": False, "error": str(e)}

if __name__ == "__main__":
    ensure_tls_certificates()
