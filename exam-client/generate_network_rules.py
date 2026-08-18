import json
import socket
from datetime import datetime
from pathlib import Path

GENERATED_DIR = Path("generated")
POLICY_FILE = GENERATED_DIR / "network-policy.json"
NFT_FILE = GENERATED_DIR / "network-rules.nft"
REPORT_FILE = GENERATED_DIR / "network-policy-report.txt"
RESOLVED_FILE = GENERATED_DIR / "network-resolved-domains.json"

def load_policy() -> dict:
    if not POLICY_FILE.exists():
        raise FileNotFoundError(
            "Politique réseau introuvable. Lancez d'abord start_exam.py ou generate_nixos_config.py."
        )
    with open(POLICY_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

def normalize_decision(value) -> str:
    if isinstance(value, bool):
        return "allowed" if value else "blocked"
    text = str(value).strip().lower()
    if text in ["true", "yes", "allowed", "allow", "enabled"]:
        return "allowed"
    if text in ["false", "no", "blocked", "block", "disabled"]:
        return "blocked"
    return text

def resolve_domain(domain: str) -> list[str]:
    try:
        results = socket.getaddrinfo(domain, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return []
    ips = []
    for result in results:
        ip = result[4][0]
        if ":" not in ip and ip not in ips:
            ips.append(ip)
    return sorted(ips)

def resolve_domains(domains: list[str]) -> dict:
    resolved = {}
    for domain in domains:
        clean_domain = domain.strip().lower()
        if clean_domain:
            resolved[clean_domain] = resolve_domain(clean_domain)
    return resolved

def generate_nft_rules(policy: dict, resolved_domains: dict) -> str:
    internet = normalize_decision(policy.get("internet", "blocked"))
    educ_access = normalize_decision(policy.get("educ_access", "blocked"))

    allowed_ips = []
    for ips in resolved_domains.values():
        allowed_ips.extend(ips)

    allowed_ips = sorted(set(allowed_ips))

    ip_elements = ", ".join(allowed_ips) if allowed_ips else ""
    default_policy = "accept" if internet == "allowed" else "drop"

    if ip_elements:
        allowed_set = f"elements = {{ {ip_elements} }}"
    else:
        allowed_set = "elements = { }"

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

def main():
    GENERATED_DIR.mkdir(exist_ok=True)

    policy = load_policy()
    allowed_domains = policy.get("allowed_domains", [])

    resolved_domains = resolve_domains(allowed_domains)
    nft_rules = generate_nft_rules(policy, resolved_domains)
    report = generate_report(policy, resolved_domains)

    NFT_FILE.write_text(nft_rules, encoding="utf-8")
    REPORT_FILE.write_text(report, encoding="utf-8")

    with open(RESOLVED_FILE, "w", encoding="utf-8") as file:
        json.dump(resolved_domains, file, indent=2, ensure_ascii=False)

    print("Règles réseau générées avec succès")
    print(f"Politique source : {POLICY_FILE}")
    print(f"Règles nftables  : {NFT_FILE}")
    print(f"Domaines résolus : {RESOLVED_FILE}")
    print(f"Rapport          : {REPORT_FILE}")

if __name__ == "__main__":
    main()