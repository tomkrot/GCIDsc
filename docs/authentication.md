# Authentication Setup

GoogleWorkspaceDsc requires a **Google Cloud service account** with
**domain-wide delegation** to access Google Workspace Admin APIs on
behalf of a super-admin.

---

## Step 1 — Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (e.g. `gwsdsc-automation`)
3. Enable the following APIs:
   - Admin SDK API
   - Groups Settings API
   - Chrome Policy API
   - Gmail API
   - Google Calendar API
   - Cloud Identity API (optional)

## Step 2 — Create a Service Account

1. Navigate to **IAM & Admin → Service Accounts**
2. Create a service account (e.g. `gwsdsc-exporter`)
3. No project-level roles are needed (it uses domain-wide delegation)
4. Create a JSON key and download it

## Step 3 — Configure Domain-Wide Delegation

1. Copy the service account's **Client ID** (numeric)
2. In the [Google Admin Console](https://admin.google.com):
   - Go to **Security → Access and data control → API controls**
   - Click **Manage Domain-Wide Delegation**
   - Click **Add new**
   - Enter the Client ID
   - Add the following OAuth scopes (one per line):

```
https://www.googleapis.com/auth/admin.directory.customer
https://www.googleapis.com/auth/admin.directory.customer.readonly
https://www.googleapis.com/auth/admin.directory.domain.readonly
https://www.googleapis.com/auth/admin.directory.group
https://www.googleapis.com/auth/admin.directory.group.readonly
https://www.googleapis.com/auth/admin.directory.group.member
https://www.googleapis.com/auth/admin.directory.group.member.readonly
https://www.googleapis.com/auth/admin.directory.orgunit
https://www.googleapis.com/auth/admin.directory.orgunit.readonly
https://www.googleapis.com/auth/admin.directory.rolemanagement
https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly
https://www.googleapis.com/auth/admin.directory.user
https://www.googleapis.com/auth/admin.directory.user.readonly
https://www.googleapis.com/auth/admin.directory.user.security
https://www.googleapis.com/auth/admin.directory.userschema
https://www.googleapis.com/auth/admin.directory.userschema.readonly
https://www.googleapis.com/auth/admin.directory.resource.calendar
https://www.googleapis.com/auth/admin.directory.resource.calendar.readonly
https://www.googleapis.com/auth/admin.directory.device.mobile.readonly
https://www.googleapis.com/auth/apps.groups.settings
https://www.googleapis.com/auth/chrome.management.policy
https://www.googleapis.com/auth/chrome.management.policy.readonly
https://www.googleapis.com/auth/gmail.settings.basic
https://www.googleapis.com/auth/gmail.settings.sharing
https://www.googleapis.com/auth/cloud-identity
https://www.googleapis.com/auth/cloud-identity.policies
https://www.googleapis.com/auth/cloud-identity.policies.readonly
https://www.googleapis.com/auth/cloud-identity.inboundsso
https://www.googleapis.com/auth/cloud-identity.inboundsso.readonly
https://www.googleapis.com/auth/cloud-identity.devices
https://www.googleapis.com/auth/cloud-identity.devices.readonly
https://www.googleapis.com/auth/cloud-identity.groups
https://www.googleapis.com/auth/cloud-identity.groups.readonly
https://www.googleapis.com/auth/cloud-platform
https://www.googleapis.com/auth/ediscovery
https://www.googleapis.com/auth/ediscovery.readonly
https://www.googleapis.com/auth/apps.alerts
https://www.googleapis.com/auth/apps.licensing
https://www.googleapis.com/auth/admin.directory.device.chromebrowsers
https://www.googleapis.com/auth/admin.directory.device.chromebrowsers.readonly
https://www.googleapis.com/auth/admin.chrome.printers
https://www.googleapis.com/auth/admin.chrome.printers.readonly
https://www.googleapis.com/auth/chrome.management.telemetry.readonly
https://www.googleapis.com/auth/admin.contact.delegation
https://www.googleapis.com/auth/admin.contact.delegation.readonly
https://www.googleapis.com/auth/admin.datatransfer
https://www.googleapis.com/auth/admin.datatransfer.readonly
https://apps-apis.google.com/a/feeds/domain/
```

## Step 4 — Store the Key in a Secrets Manager

**Never commit service account keys to Git.** Use a secrets manager:

### Option A — Google Cloud Secret Manager

```bash
# Upload the key
gcloud secrets create gwsdsc-sa-key \
  --data-file=path/to/sa-key.json

# In tenant.yaml:
credentials:
  secret_backend: google_secret_manager
  secret_ref: "gwsdsc-sa-key"
  google_project_id: "my-project"      # optional inside GCP
```

### Option B — Azure Key Vault

```bash
# Upload the key (base64-encoded)
az keyvault secret set \
  --vault-name my-vault \
  --name gwsdsc-sa-key \
  --value "$(base64 -w0 sa-key.json)"

# In tenant.yaml:
credentials:
  secret_backend: azure_key_vault
  azure_vault_url: "https://my-vault.vault.azure.net"
  azure_secret_name: "gwsdsc-sa-key"
  # Optional: explicit SP auth (otherwise DefaultAzureCredential)
  # azure_tenant_id: "..."
  # azure_client_id: "..."
  # azure_client_secret_env: "AZURE_CLIENT_SECRET"
```

### Option C — Environment Variable (CI/CD)

```bash
# Encode and set in your pipeline
export GWS_SA_KEY_JSON=$(base64 -w0 sa-key.json)

# In tenant.yaml:
credentials:
  secret_backend: env
  secret_ref: "GWS_SA_KEY_JSON"
```

## Step 5 — Configure tenant.yaml

```yaml
credentials:
  type: service_account
  secret_backend: google_secret_manager  # or azure_key_vault / env / file
  secret_ref: "gwsdsc-sa-key"
  delegated_admin_email: admin@yourdomain.com
```

The `delegated_admin_email` is the super-admin account that the service
account will impersonate via domain-wide delegation.

## Step 6 — Test

```bash
gwsdsc export --config config/tenant.yaml --resources customer
```

If successful, you should see a `customer.json` file in your artifacts
directory with your tenant's customer record.

---

## Authentication Types

| Type | Use Case | Config |
|---|---|---|
| `service_account` | Automation (pipelines, scheduled exports) | Key file + DWD |
| `adc` | Running inside Google Cloud (Cloud Build, Compute Engine) | Automatic |
| `oauth` | Local development / interactive | `credentials.json` from Cloud Console |

## Security Best Practices

- **Always** store the service account key in a secrets manager (Azure Key Vault or GCP Secret Manager)
- Never commit keys to Git or embed them in pipeline definitions
- Use environment variables to reference the key path: `$GWS_SA_KEY_PATH`
- Rotate the key regularly
- Use the **principle of least privilege** — only grant the scopes you need
- For read-only exports, use `*.readonly` scopes where available
- Audit service account usage via Cloud Audit Logs
- In Azure DevOps, use Variable Groups linked to Azure Key Vault
- In Google Cloud Build, use Secret Manager with IAM-scoped access
