# API Gap Analysis — Additional Configuration APIs

> Investigation into Google APIs not yet covered by GoogleWorkspaceDsc
> that could export additional tenant configuration data.
>
> **STATUS: ALL 13 APIS IMPLEMENTED** — see below for details.
> The framework now covers 31 resource modules across 11 Google APIs.

---

## Summary

The current framework covers 21 resource modules across the Admin SDK Directory API, Chrome Policy API, Gmail API, and Cloud Identity API. This investigation identified **13 additional APIs** that surface exportable configuration, grouped into three priority tiers based on how much configuration surface they unlock and how mature/stable the API is.

| Priority | New Modules | Configuration Surface |
|---|---|---|
| **P1 — High** | 5 | Core tenant settings, context-aware access, Vault retention, Chrome browsers, Alert Center rules |
| **P2 — Medium** | 5 | Admin Settings (legacy), Workspace Marketplace apps, license assignments, contact delegation, data transfer settings |
| **P3 — Low** | 3 | ChromeOS devices (telemetry), user invitations, Chrome printers |

---

## Priority 1 — High Value

### 1. Cloud Identity Policy API — Extended Settings (ALREADY PARTIALLY COVERED)

**Status:** The `ci_policies` module already exports policies, but the Policy API has been expanded significantly since our initial implementation. It reached GA in February 2025 with support for many additional setting families.

**What's missing from our current coverage:**

| Setting Family | Description |
|---|---|
| `data_protection` | DLP rules — detectors, conditions (CEL expressions), actions, rule scopes. These are the data protection rules for Gmail, Drive, and Chat. |
| `data_protection.detector` | Custom DLP detectors — regex patterns and word lists |
| `service_status` | Per-service on/off toggles per OU/Group (e.g. "is Drive enabled for this OU?") |
| `alerts` | System-defined alert rules and their notification settings |
| `chat`, `meet`, `classroom`, `takeout`, `sites`, `vault` | Application-specific policies not yet in our family list |
| `user_takeout` | User-level data export (Takeout) controls |

**API:** `cloudidentity.googleapis.com` v1 — `policies.list()` / `policies.get()`

**Recommendation:** Expand the `_SETTING_TYPE_FAMILIES` list in `ci_policies.py` to include all families documented at [Supported Policy API Settings](https://docs.cloud.google.com/identity/docs/concepts/supported-policy-api-settings). The API also now supports write operations for many settings, so import coverage should be updated.

**Scopes needed:** Already included (`cloud-identity.policies`).

---

### 2. Access Context Manager API — Context-Aware Access (NEW)

**What it covers:** Context-Aware Access (CAA) is the BeyondCorp zero-trust layer for Google Workspace. It defines access levels (IP range, device posture, OS version, screen lock, encryption status) and binds them to Workspace applications and OUs. This is one of the most security-critical configuration surfaces.

**Resources available via the REST API:**

| Resource | Endpoint | Export | Import |
|---|---|---|---|
| Access Policies | `accessPolicies.list` | ✅ | ✅ |
| Access Levels | `accessPolicies.accessLevels.list` | ✅ | ✅ |
| Service Perimeters (VPC SC) | `accessPolicies.servicePerimeters.list` | ✅ | ✅ |
| GCP-IAM Access Bindings | `accessPolicies.accessLevels.list` | ✅ | ✅ |

**API:** `accesscontextmanager.googleapis.com` v1

**Scopes:**
```
https://www.googleapis.com/auth/cloud-platform
```

**Why P1:** Context-Aware Access is a CISA SCuBA baseline requirement. It is configuration that directly controls who can access Workspace and under what conditions. Drift in these policies is a significant security risk.

---

### 3. Google Vault API — Retention Rules & Holds (NEW)

**What it covers:** Google Vault manages data governance — retention rules (default and custom), legal holds, and retention policies per service (Gmail, Drive, Chat, Voice, Groups). These are compliance-critical settings.

**Resources available via the REST API:**

| Resource | Endpoint | Export | Import |
|---|---|---|---|
| Matters | `matters.list` | ✅ | ✅ |
| Holds (per matter) | `matters.holds.list` | ✅ | ✅ |
| Retention rules | Not directly exposed via REST API — accessible through CI Policy API `vault.*` settings | ✅ | ⚠️ |

**API:** `vault.googleapis.com` v1

**Scopes:**
```
https://www.googleapis.com/auth/ediscovery
https://www.googleapis.com/auth/ediscovery.readonly
```

**Why P1:** Incorrect retention rules can cause irreversible data loss. Exporting and versioning Vault configuration protects against accidental purge.

---

### 4. Chrome Enterprise Core API — Managed Browser Inventory (NEW)

**What it covers:** Chrome Browser Cloud Management (CBCM) — the enterprise browser management surface. This API provides access to enrolled Chrome browser devices, their installed extensions, applied policies, OS info, and enrollment tokens. It's a separate API from the Chrome Policy API (which controls what policies *should* be applied) — CBCM shows what *is* deployed.

**Resources available via the REST API:**

| Resource | Endpoint | Export | Import |
|---|---|---|---|
| Chrome Browsers (enrolled) | `chromebrowsers.list` (Directory API v1.1beta1) | ✅ | ⚠️ (update annotated fields) |
| Browser extensions (per device) | Included in browser response | ✅ | ❌ |
| Browser policies (per device) | Included in browser response | ✅ | ❌ |
| Enrollment Tokens | `chrome/enrollmentTokens.list` | ✅ | ✅ (create/revoke) |

**API:** `admin.googleapis.com` v1.1beta1 (Directory API beta extension)

**Scopes:**
```
https://www.googleapis.com/auth/admin.directory.device.chromebrowsers
https://www.googleapis.com/auth/admin.directory.device.chromebrowsers.readonly
```

**Why P1:** Extension sprawl and unmanaged browsers are a top attack vector. Tracking the deployed browser estate, extensions, and policy compliance as versioned config is extremely valuable for security audits.

---

### 5. Alert Center API — Alert Rules & Configuration (NEW)

**What it covers:** The Alert Center contains both system-defined and admin-configured alert rules. System-defined rules cover events like suspicious logins, DLP violations, account compromises, SSO profile changes, and device compromises. Admins configure notification targets, severity levels, and on/off states.

**Resources available via the REST API:**

| Resource | Endpoint | Export | Import |
|---|---|---|---|
| Alerts (historical) | `alerts.list` | ✅ | ❌ (read-only) |
| Alert feedback | `alerts.feedback.list` | ✅ | ❌ |
| Alert settings | Partially via CI Policy API (`alerts.*` settings) | ✅ | ⚠️ |

**API:** `alertcenter.googleapis.com` v1beta1

**Scopes:**
```
https://www.googleapis.com/auth/apps.alerts
```

**Note:** Alert *rules* (the configuration of system-defined alerts) are now exposed through the Cloud Identity Policy API under the `alerts` setting family. The Alert Center API itself provides the *alerts* (events). For configuration export purposes, the CI Policy API is the primary source, but the Alert Center API provides a useful snapshot of active alerts and their states.

---

## Priority 2 — Medium Value

### 6. Admin Settings API (Legacy Email/SSO Gateway) (NEW)

**What it covers:** This is the legacy Admin Settings API (Atom/XML-based, predating the Cloud Identity Policy API). It still exposes some settings not yet available elsewhere, including SMTP gateway configuration, outbound email routing, and legacy SSO settings.

**Resources:**

| Setting | Endpoint |
|---|---|
| Outbound email gateway | `email/gateway` |
| Email routing (domain-level) | `emailrouting` |
| Legacy SSO settings | `sso/general`, `sso/signingkey` |
| Default language | `general/defaultLanguage` |
| Organisation name | `general/organizationName` |

**API:** `apps-apis.google.com` (GData/Atom XML, not REST/JSON)

**Scopes:**
```
https://apps-apis.google.com/a/feeds/domain/
```

**Caveat:** This API uses legacy GData XML format, not JSON. It is likely to be deprecated once the CI Policy API covers all these settings. Consider it a bridge for settings not yet in the Policy API.

---

### 7. Workspace Marketplace Apps Allowlist (NEW)

**What it covers:** The list of approved/blocked third-party Marketplace applications, configured per OU. This is available through the CI Policy API under the `workspace_marketplace.apps_allowlist` setting, but deserves explicit attention as a distinct configuration surface.

**API:** Already covered by CI Policy API. The `apps_allowlist` returns `application_id` values which can be resolved to application names using the Marketplace URL pattern.

**Recommendation:** Add a helper to `ci_policies.py` that enriches exported Marketplace allowlist data with human-readable application names.

---

### 8. Enterprise License Manager API (NEW)

**What it covers:** Tracks which Google Workspace licenses (SKUs) are assigned to which users. License assignments affect which features users can access and which policies apply. This is especially important for tenants with mixed license types (e.g. Enterprise + Frontline).

**Resources:**

| Resource | Endpoint | Export | Import |
|---|---|---|---|
| License assignments | `licenseAssignments.listForProduct` | ✅ | ✅ |

**API:** `licensing.googleapis.com` v1

**Scopes:**
```
https://www.googleapis.com/auth/apps.licensing
```

---

### 9. Contact Delegation API (NEW)

**What it covers:** Manages which users have delegated access to other users' contacts. This is a security-relevant configuration that determines cross-account contact visibility.

**API:** `admin.googleapis.com` — Contact Delegation sub-API

**Scopes:**
```
https://www.googleapis.com/auth/admin.contact.delegation
https://www.googleapis.com/auth/admin.contact.delegation.readonly
```

---

### 10. Data Transfer API (NEW)

**What it covers:** While primarily used for one-time transfers when offboarding users, the Data Transfer API also exposes which applications support data transfer and any pending/completed transfer records. Useful for audit of offboarding procedures.

**API:** `admin.googleapis.com` — datatransfer v1

**Scopes:**
```
https://www.googleapis.com/auth/admin.datatransfer
https://www.googleapis.com/auth/admin.datatransfer.readonly
```

---

## Priority 3 — Low Priority / Niche

### 11. ChromeOS Management Telemetry API (NEW)

**What it covers:** Telemetry data from managed ChromeOS devices — CPU usage, memory, storage, network, battery health, peripherals. This is inventory/health data rather than configuration, but can be useful for fleet management auditing.

**API:** `chromemanagement.googleapis.com` v1

**Scopes:**
```
https://www.googleapis.com/auth/chrome.management.telemetry.readonly
```

**Note:** Read-only, non-configuration data. Low priority for a DSC framework but useful for compliance reporting.

---

### 12. Cloud Identity User Invitations API (NEW)

**What it covers:** Manages unmanaged accounts (consumer Gmail accounts using your domain) — lets you invite them to become managed accounts. The API exposes the list of invitable users and pending invitations.

**API:** `cloudidentity.googleapis.com` v1 — `customers.userinvitations`

**Scopes:**
```
https://www.googleapis.com/auth/cloud-identity
```

---

### 13. Chrome Printer Management API (NEW)

**What it covers:** Manages CUPS printers and print servers for the organisation. Exports the printer fleet configuration (printer names, URIs, drivers, OU assignments).

**API:** `admin.googleapis.com` — Chrome Printer Management

**Scopes:**
```
https://www.googleapis.com/auth/admin.chrome.printers
https://www.googleapis.com/auth/admin.chrome.printers.readonly
```

---

## APIs Investigated but Not Recommended

| API | Reason for Exclusion |
|---|---|
| **Reports API** | Audit/activity logs, not configuration. Useful for SIEM, not DSC. |
| **Google Drive API** | Per-user file data, not tenant configuration. |
| **Calendar API** (user-level) | Per-user calendar data, not admin settings. |
| **People API** | User contact data, not admin configuration. |
| **Cloud Asset API** | GCP resource inventory, not Workspace config. |
| **Reseller API** | Partner/reseller management, not tenant config. |
| **Gmail API** (user email) | Per-user mailbox data, not admin configuration. |

---

## Implementation Status

All 13 APIs from the gap analysis have been implemented as resource modules.

| # | Module | Status | Resource File |
|---|---|---|---|
| 1 | CI Policy API (expanded) | ✅ Implemented | `ci_policies.py` — 90+ setting families |
| 2 | Access Context Manager | ✅ Implemented | `context_aware_access.py` |
| 3 | Google Vault | ✅ Implemented | `vault_retention.py` |
| 4 | Chrome Enterprise Core | ✅ Implemented | `chrome_browsers.py` |
| 5 | Alert Center | ✅ Implemented | `alert_center.py` |
| 6 | Admin Settings Legacy | ✅ Implemented | `admin_settings_legacy.py` |
| 7 | Marketplace Apps | ✅ Covered by `ci_policies` (`workspace_marketplace.apps_allowlist`) |
| 8 | License Manager | ✅ Implemented | `license_assignments.py` |
| 9 | Contact Delegation | ✅ Implemented | `contact_delegation.py` |
| 10 | Data Transfer | ✅ Implemented | `data_transfers.py` |
| 11 | ChromeOS Telemetry | ✅ Implemented | `chromeos_telemetry.py` |
| 12 | User Invitations | ✅ Implemented | `ci_user_invitations.py` |
| 13 | Chrome Printers | ✅ Implemented | `chrome_printers.py` |

### Final Scope

| Metric | Value |
|---|---|
| Resource modules | **31** |
| OAuth scopes | **48** |
| Google APIs used | **11** |

---

*Investigation completed March 2026 — all items implemented*
