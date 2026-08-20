from pathlib import Path
from datetime import datetime
import json
import socket
import sys

# Racine du client SecureExam :
# exam-client/
CLIENT_ROOT = Path(__file__).resolve().parents[1]
if str(CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(CLIENT_ROOT))

from config.client_settings import GENERATED_DIR
from core.logger import write_log

POLICY_FILE = GENERATED_DIR / "network-policy.json"
NFT_FILE = GENERATED_DIR / "network-rules.nft"
REPORT_FILE = GENERATED_DIR / "network-policy-report.txt"
RESOLVED_FILE = GENERATED_DIR / "network-resolved-domains.json"

def load_policy() -> dict:
    """
    Charge la politique réseau générée par generation/generate_nixos_config.py.
    """
    if not POLICY_FILE.exists():
        raise FileNotFoundError(
            f"Politique réseau introuvable : {POLICY_FILE}\n"
            "Lance d'abord generation/generate_nixos_config.py."
        )

    return json.loads(POLICY_FILE.read_text(encoding="utf-8"))

def normalize_decision(value) -> str:
    """
    Normalise une valeur booléenne ou textuelle en allowed/blocked.
    """
    if isinstance(value, bool):
        return "allowed" if value else "blocked"

    text = str(value).strip().lower()

    if text in ["true", "yes", "allowed", "allow", "enabled"]:
        return "allowed"

    if text in ["false", "no", "blocked", "block", "disabled"]:
        return "blocked"

    return text

def resolve_domain(domain: str) -> list[str]:
    """
    Résout un domaine en adresses IPv4.
    Limite connue : le filtrage par domaine via nftables reste imparfait,
    car les règles système filtrent principalement par IP.
    """
    try:
        results = socket.getaddrinfo(domain, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return []

    ips = []

    for result in results:
        ip = result[4][0]

        # On garde uniquement IPv4 pour ce prototype.
        if ":" not in ip and ip not in ips:
            ips.append(ip)

    return sorted(ips)

def resolve_domains(domains: list[str]) -> dict:
    """
    Résout la liste blanche de domaines demandée par l'enseignant.
    """
    resolved = {}

    for domain in domains:
        clean_domain = str(domain).strip().lower()

        if clean_domain:
            resolved[clean_domain] = resolve_domain(clean_domain)

    return resolved

def generate_nft_rules(policy: dict, resolved_domains: dict) -> str:
    """
    Génère les règles nftables à partir de la politique réseau.
    """
    internet = normalize_decision(policy.get("internet", "blocked"))
    educ_access = normalize_decision(policy.get("educ_access", "blocked"))

    allowed_ips = []

    for ips in resolved_domains.values():
        allowed_ips.extend(ips)

    allowed_ips = sorted(set(allowed_ips))

    ip_elements = ", ".join(allowed_ips)
    default_policy = "accept" if internet == "allowed" else "drop"

    if ip_elements:
        allowed_set = f"elements = {{ {ip_elements} }}"
    else:
        allowed_set = "# Liste blanche IP vide : aucun domaine résolu."

    return f"""#!/usr/sbin/nft -f

# Règles réseau générées automatiquement par ISEN SecureExam
# Date génération : {datetime.now().isoformat(timespec="seconds")}
# Internet        : {internet}
# Educ            : {educ_access}
# Attention       : le filtrage par domaine nécessite DNS/proxy contrôlé ou résolution IP.

table inet secure_exam {{
  set allowed_ipv4 {{
    type ipv4_addr
    flags interval
    {allowed_set}
  }}

  chain output {{
    type filter hook output priority 0;
    policy {default_policy};

    # Boucle locale : nécessaire pour les services locaux de la machine.
    oifname "lo" accept

    # Connexions déjà établies.
    ct state established,related accept

    # DNS : nécessaire si l'infrastructure autorise une résolution contrôlée.
    udp dport 53 accept
    tcp dport 53 accept

    # DHCP : utile si la machine reçoit son adresse automatiquement.
    udp sport 68 udp dport 67 accept

    # Domaines autorisés convertis en adresses IPv4 au moment de la génération.
    ip daddr @allowed_ipv4 accept

    # Accès Educ : à adapter selon l'infrastructure DSI.
    # Dans une version école, ce bloc peut pointer vers les IP/VLAN/proxy Educ.
  }}
}}
"""

def generate_report(policy: dict, resolved_domains: dict) -> str:
    """
    Génère un rapport lisible expliquant la politique réseau produite.
    """
    internet = normalize_decision(policy.get("internet", "blocked"))
    educ_access = normalize_decision(policy.get("educ_access", "blocked"))
    allowed_domains = policy.get("allowed_domains", [])

    lines = [
        "Rapport de politique réseau - ISEN SecureExam",
        "================================================",
        f"Date génération : {datetime.now().isoformat(timespec='seconds')}",
        "",
        "Politique demandée par l'enseignant :",
        f"- Internet : {internet}",
        f"- Accès Educ : {educ_access}",
        f"- Domaines autorisés : {', '.join(allowed_domains) if allowed_domains else 'aucun'}",
        "",
        "Résolution des domaines :"
    ]

    if not resolved_domains:
        lines.append("- Aucun domaine à résoudre.")
    else:
        for domain, ips in resolved_domains.items():
            if ips:
                lines.append(f"- {domain} -> {', '.join(ips)}")
            else:
                lines.append(f"- {domain} -> résolution impossible")

    lines.extend([
        "",
        "Fichiers générés :",
        f"- {NFT_FILE}",
        f"- {RESOLVED_FILE}",
        f"- {REPORT_FILE}",
        "",
        "Note technique :",
        "Le filtrage par domaine ne peut pas être garanti uniquement avec nftables,",
        "car un firewall travaille principalement avec des adresses IP.",
        "Pour une application stricte en établissement, il faut utiliser un DNS contrôlé,",
        "un proxy, une passerelle réseau, un VLAN examen ou une politique DSI dédiée.",
        "",
        "Dans cette version, la plateforme prépare les règles système exploitables",
        "sans les appliquer automatiquement afin d'éviter de couper la VM, le backend,",
        "le frontend ou l'accès Git pendant la démonstration."
    ])

    return "\n".join(lines) + "\n"

def main() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    try:
        policy = load_policy()
    except Exception as error:
        print(error)
        write_log("NETWORK_ERROR", f"Politique réseau introuvable ou invalide : {error}")
        sys.exit(1)

    allowed_domains = policy.get("allowed_domains", [])

    resolved_domains = resolve_domains(allowed_domains)
    nft_rules = generate_nft_rules(policy, resolved_domains)
    report = generate_report(policy, resolved_domains)

    NFT_FILE.write_text(nft_rules, encoding="utf-8")
    REPORT_FILE.write_text(report, encoding="utf-8")
    RESOLVED_FILE.write_text(
        json.dumps(resolved_domains, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("Règles réseau générées avec succès")
    print(f"Politique source : {POLICY_FILE}")
    print(f"Règles nftables  : {NFT_FILE}")
    print(f"Domaines résolus : {RESOLVED_FILE}")
    print(f"Rapport          : {REPORT_FILE}")

    write_log("NETWORK", f"Règles nftables générées : {NFT_FILE}")
    write_log("NETWORK", f"Rapport réseau généré : {REPORT_FILE}")

if __name__ == "__main__":
    main()
