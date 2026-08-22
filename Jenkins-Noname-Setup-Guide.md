# Jenkins Setup Guide for Noname Active Testing + GitHub

**Last updated:** August 22, 2026  
**Deployed to:** 192.168.1.100 (Rocky Linux 9)  
**Purpose:** Jenkins installation optimized for integrating **Noname Security Active Testing** with a personal GitHub repository.

This guide uses the official recommended Docker approach with Docker-in-Docker support. This is the best method because Noname Active Testing (API DAST) requires a running application target — you will almost always need to deploy an ephemeral test environment inside the pipeline.

---

## Prerequisites

- Docker CE installed and running (see Step 0 for Rocky Linux / RHEL 9)
- A personal GitHub account
- A **Classic (legacy) GitHub Personal Access Token** (recommended over fine-grained for better Jenkins compatibility)
  - Required scopes: `repo`, `admin:repo_hook`
- At least 4 GB of free RAM recommended

---

## 0. Install Docker CE on Rocky Linux / RHEL 9

Rocky Linux 9 ships with Podman by default. Docker CE conflicts with the `podman-docker` shim, so install with `--allowerasing` to replace it.

```bash
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo

sudo dnf install -y --allowerasing docker-ce docker-ce-cli containerd.io docker-buildx-plugin

sudo systemctl enable --now docker

sudo usermod -aG docker $USER
# Log out and back in for the group change to take effect
```

> **Note:** `--allowerasing` removes `podman-docker` and the `container-tools` meta-package. Podman itself is not removed.

---

## 1. Installation Steps

### Step 1.1 – Create Docker network and Docker-in-Docker

```bash
docker network create jenkins

docker run --name jenkins-docker --detach \
  --privileged --network jenkins --network-alias docker \
  --restart=always \
  --env DOCKER_TLS_CERTDIR=/certs \
  --volume jenkins-docker-certs:/certs/client \
  --volume jenkins-data:/var/jenkins_home \
  --publish 2376:2376 \
  docker:dind --storage-driver overlay2
```

> **Why `--restart=always` instead of `--rm`:** On a server, `--rm` deletes the container on exit — if the host reboots or the container crashes, it never comes back. `--restart=always` ensures the DinD container auto-restarts. The two flags are mutually exclusive in Docker; never combine them.

### Step 1.2 – Create a custom Jenkins image

Create a file named `Dockerfile` in any empty folder:

```dockerfile
FROM jenkins/jenkins:lts-jdk17

USER root

RUN apt-get update && apt-get install -y lsb-release ca-certificates curl && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && apt-get install -y docker-ce-cli && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER jenkins

RUN jenkins-plugin-cli --plugins "blueocean docker-workflow github github-branch-source pipeline-model-definition credentials-binding plain-credentials git workflow-aggregator"
```

> **Why a single-line plugin list:** The `jenkins-plugin-cli` command is sensitive to how arguments are passed inside a Dockerfile `RUN` instruction. A quoted string spanning multiple lines via backslash continuation causes the shell to inject a newline into the argument, producing an empty plugin name that results in 404 errors from the Jenkins update center. Keep the full plugin list on one line.

Build the image:

```bash
docker build -t myjenkins-noname .
```

### Step 1.3 – Run Jenkins

```bash
docker run --name jenkins --restart=on-failure --detach \
  --network jenkins \
  --env DOCKER_HOST=tcp://docker:2376 \
  --env DOCKER_CERT_PATH=/certs/client \
  --env DOCKER_TLS_VERIFY=1 \
  --publish 8080:8080 --publish 50000:50000 \
  --volume jenkins-data:/var/jenkins_home \
  --volume jenkins-docker-certs:/certs/client:ro \
  myjenkins-noname
```

### Step 1.4 – Create the admin user via init script (bypasses setup wizard)

Instead of using the browser setup wizard, drop a Groovy init script into the Jenkins home directory before first login. Jenkins executes all scripts in `init.groovy.d/` at startup.

```bash
docker exec -i jenkins bash -c 'mkdir -p /var/jenkins_home/init.groovy.d && cat > /var/jenkins_home/init.groovy.d/basic-security.groovy' << 'EOF'
import jenkins.model.*
import hudson.security.*

def instance = Jenkins.get()

def hudsonRealm = new HudsonPrivateSecurityRealm(false)
hudsonRealm.createAccount('admin', 'YOUR_PASSWORD_HERE')
instance.setSecurityRealm(hudsonRealm)

def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
strategy.setAllowAnonymousRead(false)
instance.setAuthorizationStrategy(strategy)

instance.save()
EOF

docker restart jenkins
```

After restart, log in at `http://192.168.1.100:8080` with username `admin` and the password you set above. The setup wizard is skipped entirely.

To verify the login worked from the server:

```bash
curl -s -o /dev/null -w '%{http_code}' -u admin:YOUR_PASSWORD http://localhost:8080/api/json
# Should return: 200
```

---

## 2. Plugins – What You Are Installing and Why

After the initial setup, go to **Manage Jenkins → Plugins → Available plugins** and install any that were not already included.

### Core / Must-Have Plugins

| Plugin                    | Purpose (plain English)                                                                 | Why it matters for Noname + GitHub |
|---------------------------|-----------------------------------------------------------------------------------------|------------------------------------|
| **Git**                   | Basic ability to clone and checkout Git repositories.                                   | Without this, Jenkins cannot get your code. |
| **GitHub**                | Adds GitHub-specific features on top of Git.                                            | Better authentication and status reporting to GitHub. |
| **GitHub Branch Source**  | Understands GitHub branches, pull requests, and tags automatically.                     | Powers **Multibranch Pipeline** so new branches/PRs are discovered automatically. |
| **Pipeline**              | Modern way of writing Jenkins jobs as code (`Jenkinsfile`).                             | Foundation of almost all modern CI/CD. |
| **Pipeline: GitHub**      | Extra helpers so Pipeline jobs work well with GitHub.                                   | Improves commit status checks and PR integration. |
| **Credentials Binding**   | Safely injects secrets (tokens, API keys) into pipelines without exposing them in logs. | Critical for using your GitHub token and later Noname API credentials securely. |
| **Plain Credentials**     | Allows storing simple secret text values.                                               | Needed to store your GitHub token (and Noname keys) as "Secret text". |

### Highly Recommended Plugins

| Plugin                    | Purpose (plain English)                                                                 | Why it matters for Noname + GitHub |
|---------------------------|-----------------------------------------------------------------------------------------|------------------------------------|
| **Docker Pipeline**       | Easy Docker commands inside a `Jenkinsfile` (`docker.build`, `docker.image`, etc.).     | You will need to deploy a temporary test environment so Noname can scan the running API. |
| **Docker**                | Core Docker integration.                                                                | Works together with Docker Pipeline. |
| **Blue Ocean**            | Modern, clean, visual interface for pipelines (instead of the classic Jenkins UI).      | Much easier to read and debug pipelines. Highly recommended. |
| **Pipeline Utility Steps**| Many small helpful steps (read/write files, find files, etc.).                          | Makes `Jenkinsfile` cleaner and more powerful. |
| **HTTP Request Plugin**   | Make HTTP/API calls (GET, POST, etc.) from inside a pipeline.                           | Useful if you trigger Noname scans via REST API. |
| **AnsiColor**             | Colorful console output (green success, red errors, etc.).                              | Much easier to read long build logs. |
| **Timestamper**           | Adds timestamps to every line in the console log.                                       | Helps you see how long each stage (especially Noname scans) takes. |

### Optional but Useful Later

| Plugin              | Purpose (plain English)                                      | When you might want it |
|---------------------|--------------------------------------------------------------|------------------------|
| **JUnit**           | Reads JUnit-style test result XML and shows nice reports.    | If Noname (or your tests) can export results in JUnit format. |
| **HTML Publisher**  | Publishes HTML reports so they appear inside Jenkins.        | Perfect for attaching Noname HTML security reports to the build. |

---

## 3. Add Your GitHub Token

**Recommendation:** Use your **Classic (legacy)** Personal Access Token.  
Fine-grained tokens work but are more limited and sometimes cause issues with webhooks and Multibranch Pipeline.

1. Go to **Manage Jenkins → Credentials → System → Global credentials (unrestricted)**
2. Click **Add Credentials**
3. Fill in:
   - **Kind**: Secret text
   - **Secret**: paste your Classic GitHub token
   - **ID**: `github-token`   ← keep this exact ID
   - **Description**: GitHub Classic PAT
4. Click **Create**

---

## 4. Useful Docker Commands

```bash
# View Jenkins logs
docker logs -f jenkins

# Restart Jenkins
docker restart jenkins

# Stop Jenkins
docker stop jenkins

# Start Jenkins again
docker start jenkins

# Get the initial admin password (if you did not use the init script method)
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

---

## 5. How to Use Jenkins

### Logging in

Open **http://192.168.1.100:8080** and log in with username `admin`.

### Create your first pipeline job

1. Click **New Item** on the left sidebar
2. Enter a name, select **Pipeline**, click OK
3. Scroll to the **Pipeline** section at the bottom
4. Set **Definition** to `Pipeline script from SCM`
5. Set **SCM** to `Git`, enter your repository URL
6. Set **Credentials** to the `github-token` credential you added in Step 3
7. Set **Branch Specifier** to `*/main` (or your default branch)
8. Set **Script Path** to `Jenkinsfile`
9. Click **Save**, then **Build Now**

### Create a Multibranch Pipeline (recommended for PRs)

1. Click **New Item**, enter a name, select **Multibranch Pipeline**, click OK
2. Under **Branch Sources** click **Add source → GitHub**
3. Set **Credentials** to `github-token`
4. Enter your repository URL under **Repository HTTPS URL**
5. Click **Save** — Jenkins will scan and discover all branches automatically

### Viewing build results

- The classic Jenkins UI shows a build history on the left side of each job
- For a better visual experience click **Open Blue Ocean** in the left sidebar — it shows a stage-by-stage pipeline graph with coloured pass/fail indicators

---

## 6. VulnNotes Integration (Active Testing Lab Target)

VulnNotes is a deliberately vulnerable Notes API running at **http://192.168.1.98:8000**, purpose-built for this Jenkins + Noname Active Testing lab. Use it as a live API target in your pipelines.

### What it provides

| URL | Purpose |
|-----|---------|
| `http://192.168.1.98:8000/` | Interactive dashboard — login, manage notes, BOLA Lab |
| `http://192.168.1.98:8000/docs` | Swagger UI |
| `http://192.168.1.98:8000/openapi.json` | OpenAPI 3.1 spec — import this into Active Testing |
| `http://192.168.1.98:8000/health` | Health check for pipeline smoke tests |
| `http://192.168.1.98:8000/api/seed` | POST — creates demo users and notes |

### Demo credentials (for Active Testing multi-user auth config)

| Username | Password | Role |
|----------|----------|------|
| alice | alice123 | user |
| bob | bob12345 | user |
| charlie | charlie1 | user |
| admin | admin123 | admin |

### Intentional vulnerability

`GET /api/notes/{id}`, `PUT /api/notes/{id}`, and `DELETE /api/notes/{id}` have **BOLA (API1:2023)** — any authenticated user can read, modify, or delete any note by ID without an ownership check. Active Testing should surface this as a finding after the baseline is trained.

### Sample Jenkinsfile for VulnNotes

```groovy
pipeline {
    agent any

    environment {
        TARGET_URL = 'http://192.168.1.98:8000'
    }

    stages {
        stage('Smoke Test') {
            steps {
                sh '''
                    echo "Checking VulnNotes health..."
                    curl -sf ${TARGET_URL}/health
                    echo "Verifying OpenAPI spec..."
                    curl -sf ${TARGET_URL}/openapi.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"API: {d['info']['title']} v{d['info']['version']}\")"
                '''
            }
        }

        stage('Seed Demo Data') {
            steps {
                sh 'curl -sf -X POST ${TARGET_URL}/api/seed'
            }
        }

        stage('Normal Traffic Baseline') {
            steps {
                sh '''
                    cd /home/mcropsey/notes-test
                    python3 normal_traffic.py --base-url ${TARGET_URL} --duration 60 --workers 4
                '''
            }
        }

        stage('Active Testing') {
            steps {
                // Replace with your Noname / Akamai Active Testing CLI invocation
                // Example: noname scan --spec ${TARGET_URL}/openapi.json --target ${TARGET_URL}
                echo "Run Active Testing here against ${TARGET_URL}/openapi.json"
            }
        }

        stage('BOLA Exploit (expected finding)') {
            steps {
                sh '''
                    cd /home/mcropsey/notes-test
                    python3 exploit_bola.py --base-url ${TARGET_URL}
                '''
            }
        }
    }

    post {
        always {
            echo "Pipeline complete. Check Active Testing console for BOLA finding on /api/notes/{id}."
        }
    }
}
```

### Fixing the vulnerability (Jenkins learning exercise)

1. Edit `app/main.py` on the build server — add the ownership check to `get_note`, `update_note`, and `delete_note`:
   ```python
   if note.owner_id != current_user.id:
       raise HTTPException(status_code=403, detail="Not authorized")
   ```
2. Commit and push — Jenkins picks it up automatically via Multibranch Pipeline
3. The pipeline rebuilds the container, re-runs the exploit, and Active Testing should clear the BOLA finding

---

## 7. Recommended Next Steps

1. Create a **Multibranch Pipeline** job pointing to your GitHub repository containing a `Jenkinsfile`
2. Use the **VulnNotes sample Jenkinsfile** (Section 6) as a starting point
3. Configure Noname/Akamai Active Testing credentials in **Manage Jenkins → Credentials**
4. Run the pipeline and confirm the BOLA finding appears in Active Testing
5. Apply the fix, push, re-run — confirm the finding clears

---

## Notes

- All Jenkins configuration and job data is stored in the Docker volume `jenkins-data`. It survives container restarts and recreations.
- This setup gives Jenkins the ability to run Docker commands inside pipelines, which is essential for realistic Noname testing.
- Keep your GitHub and Noname credentials only in Jenkins Credentials — never hard-code them in the `Jenkinsfile`.
- On Rocky Linux 9, use `sudo docker` until you log out and back in after adding your user to the `docker` group.
- Jenkins is on **192.168.1.100:8080**. VulnNotes (the test target) is on **192.168.1.98:8000**. Keep them separate — Jenkins orchestrates, VulnNotes is the target.

---

**Document deployed to 192.168.1.100 for Noname Active Testing integrated with Jenkins + GitHub.**
