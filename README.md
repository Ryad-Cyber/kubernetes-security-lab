# Kubernetes Security Lab — Cloud-Native Security & DevSecOps

Personal project: design, deployment, audit and hardening of a three-tier
Kubernetes application using a defense-in-depth strategy, covering the main
stages of a containerized application's security lifecycle — from the
software supply chain to runtime detection and observability.

This is a completed personal project, built end-to-end in a local, controlled
environment (not a cloud-hosted or production deployment).

## Objective

Apply defense in depth to a real Kubernetes workload:

- Software supply chain security (build).
- Continuous integration and DevSecOps controls.
- Kubernetes deployment and GitOps.
- Identity and workload security.
- Zero Trust network segmentation.
- Policy as Code.
- Runtime threat detection.
- Monitoring and observability.
- Before/after security posture benchmarking.
- Experimental validation of every protection mechanism (not configuration
  alone).

## Architecture

**Environment**: Windows 11, Docker Desktop, WSL2, Kubernetes v1.34.0 via
`kind` (cluster `security-lab`, one control-plane node and one worker, both
`Ready`, containerd runtime, Debian 12 nodes), administered with `kubectl`
and `Helm`.

**Three-tier application**:

| Tier | Stack | Namespace | Notes |
|---|---|---|---|
| Frontend | Nginx unprivileged (`nginxinc/nginx-unprivileged:alpine`) | `frontend` | ClusterIP, 1 replica |
| Backend | Python, FastAPI, Uvicorn — custom image `security-lab-backend:1.1.0` | `backend` | Deployed via Helm, ClusterIP:8000, 2 replicas |
| Database | PostgreSQL 16 Alpine | `database` | ClusterIP:5432, credentials injected via Kubernetes Secrets |

An additional `security-testing` namespace hosts the validation workloads
used to test network and policy controls. Application health and database
connectivity were verified both before and after hardening.

## Defense in depth

### 1. Network security — Cilium, eBPF, Hubble

Cilium 1.19.11 as CNI (eBPF-based), with Hubble Relay and Hubble UI for
interservice traffic observability. **8 active NetworkPolicies** implement
Zero Trust segmentation: default-deny ingress/egress, explicit allow-listing
of the only two flows the application needs (frontend → backend on
TCP/8000, backend → PostgreSQL on TCP/5432), managed DNS egress, and an
explicit block on PostgreSQL's outbound traffic.

Two unauthorized-communication tests were run from the `security-testing`
namespace against the backend and PostgreSQL. **Both were blocked**, and
Hubble logged the denials (`Policy denied DROPPED`), while the legitimate
application traffic kept working.

### 2. Identity & access management

- Permission audits with `kubectl auth can-i`.
- Kubernetes RBAC with three dedicated ServiceAccounts: `frontend-sa`,
  `backend-sa`, `database-sa`.
- `automountServiceAccountToken: false` on application workloads, verified.
- PostgreSQL credentials managed through Kubernetes Secrets, with an
  experimental check that application ServiceAccounts cannot read them.
- `.gitignore` exclusions and Gitleaks secret scanning for the repository
  itself.

### 3. Workload hardening

Pod Security Standards at the **restricted** level, enforced via Pod
Security Admission (`enforce`, `audit`, `warn`): non-root execution,
`SecurityContext` hardening, no privilege escalation, dropped Linux
capabilities, `RuntimeDefault` seccomp profile, read-only root filesystems,
CPU/memory limits, and `emptyDir` volumes sized for actual write needs. A
non-compliant Pod submitted to the cluster was rejected by Pod Security
Admission.

### 4. Security assessment — Trivy & Kubescape

**Image vulnerability baseline** (Trivy): 239 findings — 0 Critical, 56
High, 84 Medium, 81 Low, 18 Unknown. This is an initial image-vulnerability
inventory, not 239 fixed issues.

**Kubernetes misconfigurations** (Trivy config scan):

| Severity | Before | After |
|---|---:|---:|
| Critical | 0 | 0 |
| High | 9 | 0 |
| Medium | 10 | 1 |
| Low | 19 | 4 |
| **Total** | **38** | **5** |

**86.8% reduction in Kubernetes misconfigurations**, with all 9 High findings
eliminated. The rendered Helm output for the backend chart shows zero
detected misconfigurations.

**Kubescape 4.0.21** comparative scoring:

| Framework | Before | After |
|---|---:|---:|
| MITRE ATT&CK | 66.92% | 68.07% |
| NSA/CISA Kubernetes Hardening | 49.09% | 55.35% |

Kubescape's scope is broader than the Trivy scans of application manifests
alone; its scan coverage was around 83%.

### 5. Policy as Code — Kyverno

Kyverno v1.20.0 (Helm), with **4 ValidatingPolicies written in CEL**, all
enforced in `Deny` mode:

- `disallow-latest-tag` — rejects the `latest` image tag.
- `require-resource-limits` — requires CPU/memory limits.
- `require-readonly-rootfs` — requires a read-only root filesystem.
- `disallow-hostpath` — rejects `hostPath` volumes.

Four non-compliant scenarios were submitted and rejected by their matching
policy; policy reports on the actual application resources show 4/4 checks
passed, 0 failed.

### 6. Runtime security — Falco

Falco 0.45.2 (Helm), deployed as a DaemonSet with the modern eBPF driver —
**2 agents, one per node**. Two detection scenarios were validated:

1. Detecting an interactive shell opened inside a backend container.
2. Detecting a file-permission change attempt via a **custom Falco rule**
   (`Backend File Permission Change`), watching `chmod`/`fchmod`/`fchmodat`
   syscalls in backend containers at `WARNING` priority.

The read-only root filesystem prevented the permission change from actually
succeeding, while Falco independently detected the attempt — demonstrating
prevention and detection working together.

### 7. DevSecOps — GitHub Actions

Workflow: [`.github/workflows/security-pipeline.yml`](.github/workflows/security-pipeline.yml)
(`Kubernetes DevSecOps Security Pipeline`), triggered on `push`,
`pull_request` and `workflow_dispatch`:

1. Checkout.
2. `helm lint`.
3. Render Helm manifests.
4. Build the Docker image.
5. Trivy image vulnerability scan.
6. **Blocking security gate** on High/Critical Kubernetes misconfigurations.
7. **Blocking security gate** on High/Critical Helm manifest misconfigurations.
8. Gitleaks secret scanning.

Validated locally, then actually run successfully on GitHub Actions — job
`security-validation`, **status Success, duration 1m16s**:
[run 45510180907](https://github.com/Ryad-Cyber/kubernetes-security-lab/actions/runs/45510180907).

### 8. Software supply chain security — SBOM

A Software Bill of Materials was generated with **Trivy** (CycloneDX JSON
format) for the custom backend image `security-lab-backend:1.1.0`:
[`security/sbom/backend-sbom.json`](security/sbom/backend-sbom.json) (~210
KB, **103 software components** inventoried, base OS detected as Debian
13.8). This demonstrates dependency traceability and software composition
inventory — it is not a list of 103 vulnerabilities.

### 9. Software supply chain security — Cosign

Image signing with **Sigstore Cosign v3.1.5**: a password-protected
key pair was generated (private key excluded from version control via
`.gitignore`), the backend image was pushed to a **local OCI registry** and
identified by its SHA-256 digest, signed with Cosign, and the signature
published alongside it in the same local registry. Verification against
the public key succeeded, including claims validation.

Files: [`security/cosign/cosign.pub`](security/cosign/cosign.pub),
[`security/cosign/signing-config.json`](security/cosign/signing-config.json).
`security/cosign/cosign.key` is never committed.

Scope notes: the registry is local, so verification did not require a
public transparency log — this is not a full production trust chain, and no
Kubernetes admission policy currently enforces Cosign signatures.

### 10. GitOps & continuous delivery — Argo CD

Argo CD v3.6.3 (Helm chart `argo/argo-cd` 10.19.1, namespace `argocd`),
connected to the project's private GitHub repository with read-only access.
A demo GitOps application, `kubernetes-gitops-demo`
([`gitops/demo/application.yaml`](gitops/demo/application.yaml)), runs an
unprivileged Nginx Deployment + Service in `security-testing`, configured
for automatic sync with self-heal (prune disabled).

**Validation**: the application was first `Synced`/`Healthy` with 1 replica.
The manifest was then changed on GitHub (1 → 2 replicas, commit `2bec0c4`
— *"Validate Argo CD automatic GitOps synchronization"*). After an explicit
Git source refresh, Argo CD automatically applied the new desired state:
Deployment `Ready 2/2`, two Pods `Running`, application `Synced`/`Healthy`
on the new Git revision.

This validates GitOps for the `gitops-demo` application specifically, not
an automated deployment of the full three-tier architecture.

### 11. Monitoring & observability — Prometheus & Grafana

`kube-prometheus-stack` (Helm chart 93.10.0, namespace `monitoring`):
Prometheus v3.16.0, Grafana, Prometheus Operator, kube-state-metrics,
prometheus-node-exporter, ServiceMonitors — configuration in
[`monitoring/values.yaml`](monitoring/values.yaml), sized for the local
machine's available resources.

Grafana's prebuilt Kubernetes dashboards displayed real Prometheus metrics
(CPU/memory usage, per-namespace resource consumption, cluster state) — a
point-in-time capture showed 3.37% CPU and 64.9% memory, which are
observations, not benchmark results.

Prometheus collection was validated with the `up` PromQL query. An initial
check found some `kind`-internal components whose metrics endpoints were
only reachable locally; the Helm configuration was adjusted to exclude
unreachable targets. Final state: **16 active targets, all reachable**
(including both node-exporter agents).

Alertmanager is not enabled; some control-plane components were excluded
from scraping without disabling the components themselves.

## Key results

| Indicator | Result |
|---|---|
| Kubernetes cluster | 2 nodes |
| Application architecture | 3 tiers |
| NetworkPolicies | 8 |
| Kyverno policies | 4 |
| Kyverno scenarios rejected | 4 / 4 |
| Unauthorized communications blocked | 2 / 2 |
| Falco detection scenarios validated | 2 / 2 |
| Kubernetes misconfigurations | 38 → 5 |
| Misconfiguration reduction | 86.8% |
| High-severity misconfigurations | 9 → 0 |
| Software components inventoried (SBOM) | 103 |
| SBOM format | CycloneDX JSON |
| Cosign signature verification | Successful |
| Argo CD GitOps update | 1 → 2 replicas, Synced/Healthy |
| Prometheus targets reachable | 16 |
| GitHub Actions pipeline | Success (1m16s) |

## Scope & limitations

- Local `kind` cluster — not hosted on AWS, Azure or GCP.
- PostgreSQL uses ephemeral (`emptyDir`) storage; Secrets/RBAC demonstrate
  access control, not encryption at rest.
- Cosign verification used a local registry without a public transparency
  log, and signatures are not enforced at Kubernetes admission time.
- Argo CD's GitOps validation covers the `gitops-demo` application, not an
  automated rollout of the full three-tier stack.
- Alertmanager is not configured.
- Syft and HashiCorp Vault are not part of this project.

## Repository layout

```
.github/workflows/security-pipeline.yml   DevSecOps CI pipeline (GitHub Actions)
app/                                      FastAPI backend source + Dockerfile
helm/backend/                             Helm chart for the backend
helm/falco/                               Falco Helm values + custom rule
helm/kyverno/                             Kyverno Helm values
kubernetes/                               Namespaces, workloads, NetworkPolicies, RBAC, Kyverno policies
infrastructure/                           kind cluster config, Cilium Helm values
gitops/demo/                              Argo CD demo application manifest
monitoring/                               kube-prometheus-stack Helm values
security/sbom/                            Trivy-generated SBOM (CycloneDX JSON)
security/cosign/                          Cosign public key + signing config (private key excluded)
evidence/baseline/, evidence/hardened/    Trivy/Kubescape/Cilium output captured before and after hardening
tests/                                    Network-policy validation manifests
screenshots/                              Selected evidence captures
```

## Reproducing the lab

1. Create the cluster: `kind create cluster --config infrastructure/kind-config.yaml --name security-lab`.
2. Install Cilium as the CNI using `infrastructure/cilium-values.yaml`.
3. Create namespaces and core workloads: `kubectl apply -f kubernetes/`.
4. Deploy the backend with Helm: `helm install backend helm/backend/`.
5. Apply NetworkPolicies, RBAC and ServiceAccounts from `kubernetes/`.
6. Install Kyverno (`helm/kyverno/values.yaml`) and apply the policies in
   `kubernetes/kyverno/`.
7. Install Falco with `helm/falco/values.yaml` and `helm/falco/custom-rules.yaml`.
8. Install `kube-prometheus-stack` with `monitoring/values.yaml`.
9. Install Argo CD and point it at this repository; apply
   `gitops/demo/application.yaml`.
10. Run the security scans (Trivy, Kubescape, Gitleaks) — see
    `.github/workflows/security-pipeline.yml` for the exact commands used in
    CI, and `evidence/` for captured baseline/hardened output.

This lab was built and run locally; reproducing it requires Docker Desktop,
WSL2 (on Windows), `kind`, `kubectl` and `Helm`.

## Portfolio

Full write-up and context: [ryad-cyber.github.io](https://ryad-cyber.github.io/#p-k8s-security)
