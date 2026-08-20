{ config, pkgs, lib, ... }:

# ---------------------------------------------------------------------------
# Configuration NixOS générée automatiquement par la plateforme SecureExam
# ---------------------------------------------------------------------------
#
# Examen   : DEMO-PYTHON-2026
# Étudiant : ETU-DEMO-001
# Machine  : PC01
# Générée  : 2026-08-20 11:19:54
#
# Ce fichier traduit les choix de l'enseignant en configuration système NixOS.
# Il peut être importé dans /etc/nixos/configuration.nix sur une machine cible.
#
# Exemple :
#
# imports = [
#   ./exam-configuration.nix
# ];
#
# ---------------------------------------------------------------------------

let
  examId = "DEMO-PYTHON-2026";
  studentId = "ETU-DEMO-001";
  machineId = "PC01";
  examWorkspace = "/home/exam/workspace";
in
{
  # -------------------------------------------------------------------------
  # 1. Utilisateur d'examen
  # -------------------------------------------------------------------------
  #
  # L'utilisateur "exam" représente le compte utilisé pendant l'épreuve.
  # Les droits sudo dépendent uniquement du choix effectué par l'enseignant.

  users.groups.exam = {};

  users.users.exam = {
    isNormalUser = true;
    description = "Utilisateur d'examen";
    group = "exam";
    home = "/home/exam";
    createHome = true;
    extraGroups = [ ];
  };

  # -------------------------------------------------------------------------
  # 2. Droits administrateur
  # -------------------------------------------------------------------------
  #
  # sudo demandé pour l'étudiant : False
  #
  # Important :
  # sudo n'est jamais désactivé globalement.
  # Cela évite de bloquer l'administrateur de la machine.
  # Le contrôle se fait uniquement via les droits de l'utilisateur exam.

  # Sudo reste actif globalement pour l'administrateur de la machine.
  # L'utilisateur exam n'est pas dans le groupe wheel, donc il n'a pas sudo.
  security.sudo.enable = true;

  # -------------------------------------------------------------------------
  # 3. Paquets autorisés pour l'examen
  # -------------------------------------------------------------------------
  #
  # La liste provient du catalogue validé côté serveur.
  # Aucun paquet arbitraire ne doit être accepté.

  environment.systemPackages = with pkgs; [
    nano
    python3
  ];

  # -------------------------------------------------------------------------
  # 4. Espace de travail étudiant
  # -------------------------------------------------------------------------
  #
  # Le workspace est créé avec des droits limités.
  # Il correspond au dossier qui sera sauvegardé puis remis à zéro.

  systemd.tmpfiles.rules = [
    "d /home/exam 0750 exam exam -"
    "d /home/exam/workspace 0750 exam exam -"
  ];

  # -------------------------------------------------------------------------
  # 5. Politique réseau prévue
  # -------------------------------------------------------------------------
  #
  # Internet autorisé : False
  # Accès Educ autorisé : True
  # Domaines autorisés : educ.isen.fr
  #
  # Remarque importante :
  # NixOS/nftables filtre principalement par IP, port et interface.
  # Le filtrage par nom de domaine doit être traité avec un DNS contrôlé,
  # un proxy, une passerelle réseau ou une conversion domaine -> IP validée
  # par l'infrastructure de l'école.

  networking.firewall.enable = true;
  networking.nftables.enable = true;

  environment.etc."exam/network-policy.json".text = ''
{
  "internet": "blocked",
  "educ_access": "allowed",
  "allowed_domains": [
    "educ.isen.fr"
  ],
  "note": "Le filtrage par domaine doit être appliqué via DNS contrôlé, proxy, ou conversion domaine vers IP par l'infrastructure réseau."
}
  '';

  # -------------------------------------------------------------------------
  # 6. Métadonnées d'examen
  # -------------------------------------------------------------------------
  #
  # Ces informations permettent d'identifier clairement la configuration
  # appliquée à une machine donnée.

  environment.etc."exam/metadata.json".text = ''
{
  "exam_id": "DEMO-PYTHON-2026",
  "student_id": "ETU-DEMO-001",
  "machine_id": "PC01",
  "workspace": "/home/exam/workspace",
  "packages": [
    "nano",
    "python3"
  ],
  "nix_packages": [
    "nano",
    "python3"
  ],
  "sudo": false,
  "internet": false,
  "educ_access": true,
  "allowed_domains": [
    "educ.isen.fr"
  ],
  "generated_at": "2026-08-20 11:19:54"
}
  '';
}
