# SmartCloud Optimizer

**Intelligent Infrastructure Optimization & FinOps Platform**

SmartCloud Optimizer is a cloud infrastructure management and optimization platform designed to monitor resource utilization, analyze optimization opportunities, estimate infrastructure costs, and manage resource allocation.

It combines a FastAPI backend, React frontend, Docker workload optimization, and local KVM/QEMU virtual machine management.

## Features

- **Dashboard & FinOps:** Resource overview, estimated monthly costs, and optimization recommendations.
- **Live Host Monitoring:** CPU, RAM, and disk utilization of the local host.
- **Docker Autoscaling:** Demonstration environment for horizontal scaling and workload monitoring.
- **Vertical Scaling:** Adjust CPU and memory limits for supported Docker workloads.
- **KVM/QEMU Integration:** Discover and manage real local virtual machines through libvirt.
- **Website-Controlled VM Resizing:** Request VM CPU and RAM changes through the web interface.
- **Optimization Engine:** Evaluate workload metrics and generate scaling decisions.
- **Authentication & RBAC:** Authenticated access, company roles, and administrator-controlled operations.
- **Audit Trail:** Track supported resource management actions.
- **Storage Telemetry:** Monitor host storage and expose interfaces for future cloud storage integrations.

### Planned enhancement

**30-day historical-data-based optimization:** The intended future workflow is to analyze the previous 30 days of resource utilization and periodically recommend or apply resource changes. Historical data retention, scheduling, decision safeguards, and automated execution must be implemented and validated before this is described as a completed feature.

## Architecture

```text
                  Web Browser
                       |
                 React Frontend
                  localhost:3000
                       |
                   REST API
                 FastAPI :8000
                       |
          +------------+-------------+
          |            |             |
      SQLite DB    Optimizers     Monitoring
                       |
             +---------+---------+
             |                   |
        Docker Engine       libvirt / KVM
             |                   |
       Demo workloads       Linux virtual machines
```

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | React, TypeScript, Vite |
| Backend | Python, FastAPI |
| Database | SQLite, SQLAlchemy |
| Authentication | Bearer tokens, role-based access control |
| Containers | Docker, Docker Compose |
| Virtualization | KVM/QEMU, libvirt, `virsh` |
| Monitoring | psutil and Docker/libvirt telemetry |
| Load testing | k6 |
| Testing | pytest, frontend tests, production build |

## Prerequisites

The following instructions target a Linux development machine, specifically Kali Linux or a compatible Debian-based distribution.

Install or configure:

- Python 3 and a virtual environment
- Node.js and npm
- Docker Engine and the Docker Compose plugin
- QEMU/KVM and libvirt, if testing VM management
- `virsh`, `curl`, and Git

Check the installed tools:

```bash
python3 --version
node --version
npm --version
docker --version
docker compose version
virsh --version
git --version
```

For real KVM management, the machine must support hardware virtualization and have a working libvirt system connection.

## 1. Clone the repository

Replace the placeholder with the actual repository URL after publishing the project.

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd smartcloud-optimizer
```

If the repository is already cloned, open the project directory instead.

## 2. Start libvirt and verify KVM

These steps are required for real virtual machine management. They are not required merely to run the dashboard.

```bash
sudo systemctl enable --now libvirtd
sudo virsh -c qemu:///system uri
sudo virsh -c qemu:///system list --all
```

The connection should resolve to the system libvirt URI, and the VM list should load successfully.

If your system uses modular libvirt daemons instead of the traditional `libvirtd` service, start the appropriate services for that installation.

Check the target VM:

```bash
sudo virsh -c qemu:///system dominfo sco-test-vm
```

Replace `sco-test-vm` with the name of your own test VM.

**Safety:** use a disposable test VM for demonstrations. Never test shutdown-dependent resizing on a production guest.

## 3. Configure and start the backend

Open a terminal at the project root:

```bash
cd smartcloud-optimizer
```

Activate the existing virtual environment:

```bash
source backend/venv/bin/activate
```

If the virtual environment does not exist, create it and install the project's declared dependencies:

```bash
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install -r backend/requirements.txt
```

Configure any required environment variables using the project's environment template and documentation. In particular, use a strong secret key and secure credentials before exposing the service beyond localhost.

Start the API:

```bash
cd backend
../backend/venv/bin/python -m uvicorn main:app \
  --host 127.0.0.1 --port 8000 --reload
```

Keep this terminal open.

Verify the API in another terminal:

```bash
curl -i http://127.0.0.1:8000/api/health
```

Expected: HTTP 200 and a JSON response indicating the backend is available.

API documentation, when enabled:

- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

## 4. Start the frontend

Open a second terminal:

```bash
cd smartcloud-optimizer/frontend
npm install
npm run dev
```

Open the URL printed by Vite. The default development URL is:

**http://localhost:3000**

If Vite selects another port, use the URL printed in the terminal.

Sign in with a locally configured administrator account. Do not publish passwords, bearer tokens, or production secrets in this repository or its README.

## 5. Verify the application

Check the backend:

```bash
curl -i http://127.0.0.1:8000/api/health
```

Check the frontend's proxied health endpoint, if the Vite proxy is configured:

```bash
curl -i http://localhost:3000/api/health
```

Run the backend tests from the repository root:

```bash
./backend/venv/bin/python -m pytest backend/tests/ -q
```

Run the frontend tests and production build:

```bash
cd frontend
npm test -- --run
npm run build
```

These commands validate the automated tests and build. They do not replace testing against the actual Docker and KVM infrastructure.

## 6. Demonstrate real VM resizing

This demonstration shows website-controlled resource allocation on a local KVM virtual machine.

### Before recording

1. Start libvirt.
2. Start the backend and frontend.
3. Confirm that the test VM exists and is running.
4. Sign in as an authorized administrator.
5. Open **Hosting & VMs → KVM**.
6. Record the VM's current CPU and RAM allocation.

For the test VM used during development, the domain name was `sco-test-vm`.

### Record the initial allocation

On the host:

```bash
sudo virsh -c qemu:///system dominfo sco-test-vm

sudo virsh -c qemu:///system dumpxml sco-test-vm \
  | grep -E '<memory|<currentMemory|<vcpu'
```

Keep the output visible for the recording.

### Perform the resize through the website

1. Open the VM management page.
2. Select the test VM.
3. Enter the desired CPU and memory allocation.
4. Review the operation and any shutdown requirement.
5. Submit the authorized resize request.
6. Wait for the operation and its verification to finish.

For example, you can demonstrate changing the configured RAM from 512 MiB to 1024 MiB, provided the VM configuration, guest support, and host capacity permit the operation.

### Verify the actual result

Run the same commands again:

```bash
sudo virsh -c qemu:///system dominfo sco-test-vm

sudo virsh -c qemu:///system dumpxml sco-test-vm \
  | grep -E '<memory|<currentMemory|<vcpu'
```

Compare the initial and final values. For 1 GiB, the memory value is typically:

```xml
<memory unit='KiB'>1048576</memory>
```

Also check the application's result and audit trail.

**A successful demonstration requires the real libvirt configuration to reflect the requested allocation.** A changed UI value alone is insufficient. Live allocation, persistent configuration, and guest-visible memory may differ depending on the resize mechanism.

## 7. Automatic optimization: current behavior versus future work

The platform contains optimization logic that can evaluate metrics and produce scaling decisions. The unified optimizer and KVM optimizer have separate configurations.

For safety, the KVM optimizer defaults to disabled and `DRY_RUN`. In this mode, it evaluates metrics and produces decisions without automatically applying resource changes.

Before enabling automatic execution, verify:

- Guest-level CPU and memory telemetry is available.
- Sustained-load thresholds and sampling intervals behave correctly.
- Scale-up and scale-down limits are enforced.
- Host CPU and RAM safety reserves are respected.
- Shutdown-required operations are handled explicitly.
- Resource changes are verified independently through libvirt.
- Every execution is recorded in the audit trail.
- Failure cases do not incorrectly update database state.

### Planned 30-day optimization workflow

The intended future workflow is:

1. Collect and retain historical workload metrics.
2. Analyze the previous 30 days of utilization.
3. Estimate appropriate CPU and memory allocations.
4. Generate a proposed resource adjustment.
5. Apply the adjustment only when policy and safety checks permit it.
6. Verify the real allocation and record the result.
7. Repeat on the configured schedule.

This requires a persistent metrics history, a scheduling mechanism, clear handling of missing data, and tested rollback or recovery behavior. A periodic schedule by itself does not constitute a reliable 30-day optimization engine.

## 8. Troubleshooting

### Backend is unavailable

```bash
curl -v http://127.0.0.1:8000/api/health
```

Check the backend terminal for startup errors, missing dependencies, or database initialization failures.

### Frontend API requests fail

Confirm that the backend is listening on port 8000 and that the frontend development proxy targets the correct API address.

### KVM domains cannot be discovered

```bash
systemctl is-active libvirtd
sudo virsh -c qemu:///system list --all
```

Check libvirt permissions and the backend's configured libvirt connection.

### VM resize fails

```bash
sudo virsh -c qemu:///system dominfo sco-test-vm
sudo virsh -c qemu:///system dumpxml sco-test-vm
```

Check maximum configured memory, vCPU limits, host capacity, VM policy, guest support, and whether a shutdown is required.

### Authentication returns HTTP 401

Sign in again through the website. Ensure the browser has a valid token and that the backend's authentication configuration matches the running environment.

## 9. Repository hygiene

Before pushing to GitHub:

```bash
git status --short
git check-ignore .env backend/smartcloud.db
```

Review the results and your `.gitignore`. Ensure that secrets, tokens, local databases containing sensitive information, virtual environments, `node_modules`, and generated build files are excluded as appropriate.

Do not commit real credentials or private keys.

## 10. Push to GitHub

If the repository has already been initialized:

```bash
git add README.md
git status
git commit -m "docs: add project README and setup instructions"
git push
```

To include other reviewed project changes, stage those files explicitly rather than blindly committing every untracked file.

## Project status

- [x] Backend and frontend implemented
- [x] Automated backend and frontend tests previously passed during development
- [x] Local monitoring and Docker workload optimization implemented
- [x] KVM domain discovery and authenticated access verified
- [x] Manual website-triggered VM resizing verified against libvirt
- [ ] Automatic KVM scale-up and scale-down validated end-to-end
- [ ] Persistent 30-day historical optimization and scheduling implemented and tested

## License

Add the license appropriate for your project before publishing the repository.
