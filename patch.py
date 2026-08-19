from pathlib import Path
import re

MAIN = Path("backend/main.py")
TS = Path("frontend/src/app/app.ts")
HTML = Path("frontend/src/app/app.html")
CSS = Path("frontend/src/app/app.css")

main = MAIN.read_text(encoding="utf-8")
ts = TS.read_text(encoding="utf-8")
html = HTML.read_text(encoding="utf-8")
css = CSS.read_text(encoding="utf-8")

# =========================
# BACKEND
# =========================

backend_block = r'''
def count_package_usage_in_configs(package_name: str, nix_name: str | None = None) -> int:
    targets = {package_name}

    if nix_name:
        targets.add(nix_name)

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT packages
        FROM exam_configs
    """)

    rows = cursor.fetchall()
    connection.close()

    usage_count = 0

    for row in rows:
        try:
            config_packages = json.loads(row["packages"])
        except Exception:
            continue

        if any(package in targets for package in config_packages):
            usage_count += 1

    return usage_count


@app.get("/packages/management")
def get_packages_management(
    current_teacher: dict = Depends(get_current_teacher)
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            nix_name,
            display_name,
            description,
            is_active,
            created_at,
            updated_at
        FROM package_catalog
        ORDER BY display_name ASC
    """)

    rows = cursor.fetchall()
    connection.close()

    packages = []

    for row in rows:
        package = package_row_to_public_dict(row)
        usage_count = count_package_usage_in_configs(row["name"], row["nix_name"])

        package["usageCount"] = usage_count
        package["canDelete"] = usage_count == 0

        packages.append(package)

    return {
        "count": len(packages),
        "packages": packages
    }


@app.delete("/packages/{package_id}")
def delete_package(
    package_id: int,
    current_teacher: dict = Depends(get_current_teacher)
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            nix_name,
            display_name,
            description,
            is_active,
            created_at,
            updated_at
        FROM package_catalog
        WHERE id = ?
    """, (
        package_id,
    ))

    package = cursor.fetchone()

    if package is None:
        connection.close()
        raise HTTPException(
            status_code=404,
            detail="Paquet introuvable."
        )

    usage_count = count_package_usage_in_configs(
        package["name"],
        package["nix_name"]
    )

    if usage_count > 0:
        connection.close()
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Ce paquet est déjà utilisé dans une ou plusieurs configurations. Il peut être désactivé, mais pas supprimé.",
                "usageCount": usage_count
            }
        )

    cursor.execute("""
        DELETE FROM package_catalog
        WHERE id = ?
    """, (
        package_id,
    ))

    connection.commit()
    connection.close()

    return {
        "message": "Paquet supprimé définitivement du catalogue.",
        "deletedPackageId": package_id
    }


'''

if 'def count_package_usage_in_configs' not in main:
    marker = '@app.get("/packages/search/{package_query}")'
    if marker not in main:
        marker = '@app.get("/packages")'
    main = main.replace(marker, backend_block + "\n" + marker, 1)

MAIN.write_text(main, encoding="utf-8")

# =========================
# FRONTEND TS
# =========================

if "interface PackageManagementItem" not in ts:
    insert_after = re.search(r'interface PackageSearchResponse \{.*?\n\}', ts, flags=re.S)
    interface_block = r'''
interface PackageManagementItem extends PackageCatalogItem {
  usageCount: number;
  canDelete: boolean;
}

interface PackageManagementResponse {
  count: number;
  packages: PackageManagementItem[];
}
'''
    if insert_after:
        ts = ts[:insert_after.end()] + "\n" + interface_block + ts[insert_after.end():]
    else:
        ts = interface_block + "\n" + ts

if "showPackageDeleteModal" not in ts:
    ts = ts.replace(
'''  selectedPackageCandidateNixName = '';
''',
'''  selectedPackageCandidateNixName = '';

  showPackageDeleteModal = false;
  packageManagementLoading = false;
  packageManagementItems: PackageManagementItem[] = [];
  selectedPackageIdsToDelete = new Set<number>();
''',
1
)

management_methods = r'''  openPackageDeleteModal(): void {
    this.showPackageDeleteModal = true;
    this.selectedPackageIdsToDelete.clear();
    this.loadPackageManagementItems();
    this.refreshView();
  }

  closePackageDeleteModal(): void {
    this.showPackageDeleteModal = false;
    this.selectedPackageIdsToDelete.clear();
    this.refreshView();
  }

  loadPackageManagementItems(): void {
    const headers = this.getTeacherHeaders();

    this.packageManagementLoading = true;

    this.http.get<PackageManagementResponse>(
      `${this.apiUrl}/packages/management`,
      { headers }
    ).subscribe({
      next: (data) => {
        this.packageManagementItems = data.packages;
        this.packageManagementLoading = false;
        this.refreshView();
      },
      error: (err) => {
        console.error(err);
        this.error = "Erreur lors du chargement des paquets.";
        this.packageManagementLoading = false;
        this.refreshView();
      }
    });
  }

  isPackageSelectedForDeletion(packageId: number): boolean {
    return this.selectedPackageIdsToDelete.has(packageId);
  }

  togglePackageManagementSelection(packageId: number, checked: boolean): void {
    if (checked) {
      this.selectedPackageIdsToDelete.add(packageId);
    } else {
      this.selectedPackageIdsToDelete.delete(packageId);
    }

    this.refreshView();
  }

  getSelectedPackageDeleteCount(): number {
    return this.selectedPackageIdsToDelete.size;
  }

  deletePackageManagementItem(packageItem: PackageManagementItem): void {
    this.error = '';
    this.success = '';

    if (!packageItem.canDelete) {
      this.error = "Ce paquet est utilisé dans une configuration. Désactive-le au lieu de le supprimer.";
      this.refreshView();
      return;
    }

    const confirmed = window.confirm(
      `Supprimer définitivement le paquet "${packageItem.displayName}" du catalogue ?`
    );

    if (!confirmed) {
      return;
    }

    const headers = this.getTeacherHeaders();

    this.packageManagementLoading = true;

    this.http.delete<{ message: string }>(
      `${this.apiUrl}/packages/${packageItem.id}`,
      { headers }
    ).subscribe({
      next: (data) => {
        this.success = data.message;
        this.selectedPackageIdsToDelete.delete(packageItem.id);
        this.loadActivePackages();
        this.loadPackageManagementItems();
        this.packageManagementLoading = false;
        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        if (err.status === 409 && err.error?.detail?.message) {
          this.error = err.error.detail.message;
        } else if (typeof err.error?.detail === 'string') {
          this.error = err.error.detail;
        } else {
          this.error = "Suppression impossible.";
        }

        this.packageManagementLoading = false;
        this.refreshView();
      }
    });
  }

  deleteSelectedPackages(): void {
    const selectedPackages = this.packageManagementItems.filter(
      packageItem =>
        this.selectedPackageIdsToDelete.has(packageItem.id) &&
        packageItem.canDelete
    );

    if (selectedPackages.length === 0) {
      this.error = "Sélectionne au moins un paquet supprimable.";
      this.refreshView();
      return;
    }

    const confirmed = window.confirm(
      `Supprimer définitivement ${selectedPackages.length} paquet(s) du catalogue ?`
    );

    if (!confirmed) {
      return;
    }

    const headers = this.getTeacherHeaders();

    this.packageManagementLoading = true;

    const deleteNext = (index: number): void => {
      if (index >= selectedPackages.length) {
        this.success = "Paquets sélectionnés supprimés avec succès.";
        this.selectedPackageIdsToDelete.clear();
        this.loadActivePackages();
        this.loadPackageManagementItems();
        this.packageManagementLoading = false;
        this.refreshView();
        return;
      }

      const packageItem = selectedPackages[index];

      this.http.delete<{ message: string }>(
        `${this.apiUrl}/packages/${packageItem.id}`,
        { headers }
      ).subscribe({
        next: () => {
          deleteNext(index + 1);
        },
        error: (err) => {
          console.error(err);
          this.error = `Suppression interrompue sur ${packageItem.displayName}.`;
          this.packageManagementLoading = false;
          this.refreshView();
        }
      });
    };

    deleteNext(0);
  }

  disablePackageManagementItem(packageItem: PackageManagementItem): void {
    const headers = this.getTeacherHeaders();

    this.packageManagementLoading = true;

    this.http.patch<{ message: string }>(
      `${this.apiUrl}/packages/${packageItem.id}/disable`,
      {},
      { headers }
    ).subscribe({
      next: (data) => {
        this.success = data.message;
        this.loadActivePackages();
        this.loadPackageManagementItems();
        this.packageManagementLoading = false;
        this.refreshView();
      },
      error: (err) => {
        console.error(err);
        this.error = "Désactivation impossible.";
        this.packageManagementLoading = false;
        this.refreshView();
      }
    });
  }

'''

if "openPackageDeleteModal(): void" not in ts:
    marker = "  togglePackageCreationForm(): void {"
    if marker not in ts:
        marker = "  createPackage(): void {"
    ts = ts.replace(marker, management_methods + "\n" + marker, 1)

TS.write_text(ts, encoding="utf-8")

# =========================
# FRONTEND HTML
# =========================

delete_button = '''
              <button
                type="button"
                class="btn-danger-outline package-delete-manager-button"
                (click)="openPackageDeleteModal()">
                <i data-lucide="trash-2"></i>
                Gérer les suppressions
              </button>
'''

if "openPackageDeleteModal()" not in html:
    create_index = html.find('(click)="createPackage()"')
    if create_index != -1:
        button_start = html.rfind("<button", 0, create_index)
        html = html[:button_start] + delete_button + "\n" + html[button_start:]

modal_block = '''
<div class="modal-backdrop package-management-backdrop" *ngIf="showPackageDeleteModal">
  <div class="package-management-modal">
    <div class="package-management-header">
      <div>
        <h2>
          <i data-lucide="trash-2"></i>
          Gestion des paquets
        </h2>
        <p>
          Supprimez les paquets non utilisés ou désactivez ceux déjà présents dans des configurations.
        </p>
      </div>

      <button
        type="button"
        class="icon-button"
        (click)="closePackageDeleteModal()">
        <i data-lucide="x"></i>
      </button>
    </div>

    <div class="package-management-actions">
      <button
        type="button"
        class="btn-danger"
        (click)="deleteSelectedPackages()"
        [disabled]="packageManagementLoading || getSelectedPackageDeleteCount() === 0">
        <i data-lucide="trash-2"></i>
        Supprimer la sélection
      </button>

      <button
        type="button"
        class="secondary-button"
        (click)="loadPackageManagementItems()"
        [disabled]="packageManagementLoading">
        <i data-lucide="refresh-cw"></i>
        Actualiser
      </button>
    </div>

    <div class="package-management-loading" *ngIf="packageManagementLoading">
      Chargement...
    </div>

    <div class="package-management-table-wrapper" *ngIf="!packageManagementLoading">
      <table class="package-management-table">
        <thead>
          <tr>
            <th>Sélection</th>
            <th>Paquet</th>
            <th>NixOS</th>
            <th>Statut</th>
            <th>Utilisation</th>
            <th>Action</th>
          </tr>
        </thead>

        <tbody>
          <tr *ngFor="let packageItem of packageManagementItems">
            <td>
              <input
                type="checkbox"
                [checked]="isPackageSelectedForDeletion(packageItem.id)"
                [disabled]="!packageItem.canDelete"
                (change)="togglePackageManagementSelection(packageItem.id, $any($event.target).checked)">
            </td>

            <td>
              <strong>{{ packageItem.displayName }}</strong>
              <small>{{ packageItem.name }}</small>
            </td>

            <td>
              <code>{{ packageItem.nixName }}</code>
            </td>

            <td>
              <span class="status-pill active" *ngIf="packageItem.isActive">Actif</span>
              <span class="status-pill disabled" *ngIf="!packageItem.isActive">Désactivé</span>
            </td>

            <td>
              <span *ngIf="packageItem.usageCount === 0" class="usage-free">
                Non utilisé
              </span>

              <span *ngIf="packageItem.usageCount > 0" class="usage-locked">
                {{ packageItem.usageCount }} config(s)
              </span>
            </td>

            <td>
              <button
                type="button"
                class="table-danger-button"
                *ngIf="packageItem.canDelete"
                (click)="deletePackageManagementItem(packageItem)">
                <i data-lucide="trash-2"></i>
                Supprimer
              </button>

              <button
                type="button"
                class="table-warning-button"
                *ngIf="!packageItem.canDelete && packageItem.isActive"
                (click)="disablePackageManagementItem(packageItem)">
                Désactiver
              </button>

              <span
                class="locked-text"
                *ngIf="!packageItem.canDelete && !packageItem.isActive">
                Protégé
              </span>
            </td>
          </tr>

          <tr *ngIf="packageManagementItems.length === 0">
            <td colspan="6" class="empty-table-message">
              Aucun paquet dans le catalogue.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</div>
'''

if "package-management-modal" not in html:
    html += "\n" + modal_block

HTML.write_text(html, encoding="utf-8")

# =========================
# CSS
# =========================

css_block = r'''
.btn-danger-outline {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 42px;
  padding: 0 16px;
  border-radius: 12px;
  border: 1px solid rgba(220, 38, 38, 0.25);
  background: #fff;
  color: #b91c1c;
  font-weight: 900;
  cursor: pointer;
  transition: 0.18s ease;
}

.btn-danger-outline:hover {
  background: #fef2f2;
  border-color: rgba(220, 38, 38, 0.45);
}

.package-delete-manager-button {
  margin-right: 10px;
}

.package-management-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.42);
  backdrop-filter: blur(5px);
}

.package-management-modal {
  width: min(1120px, 96vw);
  max-height: 86vh;
  overflow: hidden;
  border-radius: 24px;
  background: #fff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.24);
}

.package-management-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 24px 26px 18px;
  border-bottom: 1px solid #e2e8f0;
}

.package-management-header h2 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 22px;
  color: #111827;
}

.package-management-header p {
  margin: 8px 0 0;
  color: #64748b;
}

.package-management-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 26px;
  border-bottom: 1px solid #e2e8f0;
}

.btn-danger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 0 16px;
  border: 0;
  border-radius: 12px;
  background: #dc2626;
  color: #fff;
  font-weight: 900;
  cursor: pointer;
}

.btn-danger:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.package-management-loading {
  padding: 28px;
  color: #64748b;
  font-weight: 800;
}

.package-management-table-wrapper {
  max-height: 52vh;
  overflow: auto;
}

.package-management-table {
  width: 100%;
  border-collapse: collapse;
}

.package-management-table th,
.package-management-table td {
  padding: 14px 16px;
  border-bottom: 1px solid #e2e8f0;
  text-align: left;
  vertical-align: middle;
}

.package-management-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #f8fafc;
  color: #334155;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.package-management-table td strong {
  display: block;
  color: #111827;
}

.package-management-table td small {
  display: block;
  margin-top: 3px;
  color: #64748b;
  font-weight: 700;
}

.package-management-table code {
  padding: 4px 8px;
  border-radius: 8px;
  background: #f1f5f9;
  color: #0f172a;
  font-weight: 800;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 900;
}

.status-pill.active {
  background: #dcfce7;
  color: #047857;
}

.status-pill.disabled {
  background: #f1f5f9;
  color: #64748b;
}

.usage-free {
  color: #047857;
  font-weight: 900;
}

.usage-locked {
  color: #b45309;
  font-weight: 900;
}

.table-danger-button,
.table-warning-button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 0;
  border-radius: 10px;
  padding: 8px 12px;
  font-weight: 900;
  cursor: pointer;
}

.table-danger-button {
  background: #fef2f2;
  color: #b91c1c;
}

.table-warning-button {
  background: #fffbeb;
  color: #b45309;
}

.locked-text {
  color: #64748b;
  font-weight: 900;
}

.empty-table-message {
  text-align: center !important;
  color: #64748b;
  font-weight: 800;
}

@media (max-width: 760px) {
  .package-management-modal {
    width: 96vw;
    max-height: 90vh;
  }

  .package-management-actions {
    flex-direction: column;
  }

  .package-management-table {
    min-width: 820px;
  }
}
'''

if "package-management-modal" not in css:
    css += "\n" + css_block

CSS.write_text(css, encoding="utf-8")

print("Patch suppression/gestion paquets appliqué ✅")
