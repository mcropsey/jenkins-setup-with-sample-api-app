# Jenkins + GitHub Integration Guide

**Environment**
- Jenkins: `http://192.168.1.100:8080` (running in Docker on Rocky Linux 9)
- Repository: https://github.com/mcropsey/jenkins-setup-with-sample-api-app
- Target under test: VulnNotes API at `http://192.168.1.98:8000`

This guide connects Jenkins to a GitHub repository and gets a working pipeline running against a live API target. It assumes Jenkins is already installed and past the initial setup wizard, with an admin login working.

The path is deliberately incremental: prove the connection first, then build the real pipeline, then turn on the heavier stages once the environment is confirmed. Each step is verifiable before moving to the next.

---

## 1. Create a GitHub Personal Access Token

On GitHub (not Jenkins): **Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token (classic)**.

- **Note:** something identifiable, e.g. `jenkins-noname`
- **Expiration:** your choice (90 days is reasonable for a lab)
- **Scopes:** check `repo` (full) and `admin:repo_hook`

Generate it and **copy the `ghp_...` token immediately** — GitHub shows it only once.

Use a **classic** token rather than fine-grained. Fine-grained tokens work for basic cloning but often trip over webhook registration and Multibranch discovery.

---

## 2. Store the token in Jenkins

**Manage Jenkins → Credentials → System → Global credentials (unrestricted) → Add Credentials**

- **Kind:** Username with password
- **Scope:** Global
- **Username:** your GitHub username
- **Password:** the `ghp_...` token
- **ID:** `github-token`  ← type this exactly; pipelines reference it by this name
- **Description:** `GitHub PAT for Noname lab`

Click **Create**. The credential appears under Global.

> The ID `github-token` is not cosmetic. Every pipeline in this guide looks the credential up by that exact string. If you name it something else, update the pipelines to match.

---

## 3. Smoke test the connection

Before building anything real, confirm Jenkins can authenticate to GitHub and check out the repo. This catches credential, network, and permission problems early, in isolation.

1. **New Item** → name it `github-smoke-test` → select **Pipeline** (the plain one, **not** Multibranch Pipeline) → **OK**
2. Scroll to the **Pipeline** section → leave **Definition** as **Pipeline script**
3. Paste this script:

```groovy
pipeline {
    agent any
    stages {
        stage('Checkout') {
            steps {
                git branch: 'main',
                    url: 'https://github.com/mcropsey/jenkins-setup-with-sample-api-app.git',
                    credentialsId: 'github-token'
            }
        }
        stage('Show files') {
            steps {
                sh 'ls -la'
                sh 'echo "Checkout succeeded — Jenkins can reach GitHub."'
            }
        }
    }
}
```

4. **Save** → **Build Now**

### Reading the result

Open the build (under Build History) → **Console Output**, or just check the Status page:

- **Green check / "Finished: SUCCESS"** → connection works.
- A **git revision hash** and **`refs/remotes/origin/main`** on the status page confirm the repo and branch were actually cloned.
- **Red / FAILURE** → the console names the cause, usually a credential ID mismatch, auth failure, or the agent being unable to reach github.com.

Once this is green, the GitHub connection is proven. This job can be deleted later; it exists only to verify the link.

> **Note on names:** `github-smoke-test` is the Jenkins *job* name. `jenkins-setup-with-sample-api-app` is the *repo* name. The job's status page shows the repo URL only because the script told it to clone that repo — the two are unrelated names that happen to appear together.

---

## 4. Add a Jenkinsfile to the repository

A `Jenkinsfile` is a plain text file named exactly `Jenkinsfile` (capital J, no extension) in the repo root. It defines what the pipeline does. A Multibranch Pipeline only builds branches that contain one — without it, there is nothing to build.

### Commit it via the GitHub website (no local git required)

1. Open the repo → confirm you're on the **main** branch
2. **Add file → Create new file**
3. Filename: `Jenkinsfile` (capital J, no extension — placed in the repo root)
4. Paste the contents below
5. Scroll down → **Commit changes** → commit directly to `main`

### Jenkinsfile contents

```groovy
pipeline {
    agent any

    environment {
        TARGET_URL = 'http://192.168.1.98:8000'
    }

    stages {
        stage('Checkout') {
            steps {
                git branch: 'main',
                    url: 'https://github.com/mcropsey/jenkins-setup-with-sample-api-app.git',
                    credentialsId: 'github-token'
                sh 'ls -la'
            }
        }

        stage('Reach VulnNotes') {
            steps {
                sh 'echo "Checking VulnNotes health..."'
                sh 'curl -sf ${TARGET_URL}/health'
                sh 'echo "Fetching OpenAPI spec..."'
                sh 'curl -sf ${TARGET_URL}/openapi.json -o /dev/null && echo "OpenAPI spec reachable"'
            }
        }

        stage('Seed Demo Data') {
            steps {
                sh 'curl -sf -X POST ${TARGET_URL}/api/seed && echo "Seeded"'
            }
        }

        stage('Normal Traffic Baseline') {
            steps {
                echo 'STUB: would run normal_traffic.py from the workspace here.'
            }
        }

        stage('Active Testing') {
            steps {
                echo "STUB: run Noname/Akamai Active Testing against ${TARGET_URL}/openapi.json here."
            }
        }

        stage('BOLA Exploit (expected finding)') {
            steps {
                echo 'STUB: would run exploit_bola.py from the workspace here.'
            }
        }
    }

    post {
        always {
            echo 'Pipeline complete.'
        }
    }
}
```

### Two deliberate choices in this Jenkinsfile

**The Python stages are stubbed.** Jenkins runs `sh` steps *inside its Docker container*, which may not have `python3` or the `requests` library. Leaving `normal_traffic.py` and `exploit_bola.py` as `echo` stubs keeps the first real build green. They get switched on in Step 6 after the environment is confirmed.

**No hardcoded host paths.** The scripts live in the checked-out workspace, so the pipeline runs them from there — not from a fixed path like `/home/mcropsey/notes-test`. That path only exists on the host, not inside the container, and would break the build.

---

## 5. Create the Multibranch Pipeline

Now that the repo has a Jenkinsfile, create the job that discovers and builds it.

1. **New Item** → name it (e.g. `vulnnotes-pipeline`) → select **Multibranch Pipeline** → **OK**
2. Under **Branch Sources** → **Add source → GitHub**
3. **Credentials:** select `github-token`
4. **Repository HTTPS URL:** `https://github.com/mcropsey/jenkins-setup-with-sample-api-app.git`
5. **Save**

Jenkins scans the repo, finds the `Jenkinsfile` on `main`, and starts a build automatically.

### What to expect on the first build

- **Checkout**, **Reach VulnNotes**, and **Seed Demo Data** run for real. Reach VulnNotes and Seed require VulnNotes to be live at `192.168.1.98:8000` and reachable from the Jenkins container.
- The last three stages just print their stub messages.
- View the run in the classic UI, or click **Open Blue Ocean** for a stage-by-stage graph.

If **Reach VulnNotes** fails, the Jenkins container can't reach the target. Confirm VulnNotes is running and that the container has network access to `192.168.1.98:8000` (see Step 6 checks).

---

## 6. Un-stub the Python stages

Once the pipeline builds green with stubs, confirm the container can actually run the scripts, then switch them on.

### Check the container environment

From the Jenkins host:

```bash
# Does the Jenkins container have python3?
docker exec jenkins python3 --version

# Does it have the requests library?
docker exec jenkins python3 -c "import requests; print(requests.__version__)"

# Can the container reach VulnNotes?
docker exec jenkins curl -sf http://192.168.1.98:8000/health && echo " OK"
```

- If `python3` is missing or `import requests` fails, install them (see below).
- If the curl check fails, it's a networking problem between the container and the target, not a pipeline problem.

### If python3 / requests are missing

The cleanest fix is to bake them into the custom Jenkins image (add to the `Dockerfile`, rebuild, recreate the container). A quick lab-only alternative is to install at runtime, but that doesn't survive container recreation:

```bash
docker exec -u root jenkins bash -c "apt-get update && apt-get install -y python3 python3-requests"
```

### Switch the stages on

Edit the `Jenkinsfile` in the repo and replace the two stubbed stages:

```groovy
stage('Normal Traffic Baseline') {
    steps {
        sh 'python3 normal_traffic.py --base-url ${TARGET_URL} --duration 60 --workers 4'
    }
}
```

```groovy
stage('BOLA Exploit (expected finding)') {
    steps {
        sh 'python3 exploit_bola.py --base-url ${TARGET_URL}'
    }
}
```

Commit to `main`. The Multibranch Pipeline picks up the change on its next scan (or trigger it manually with **Scan Repository Now**).

---

## 7. Wire in Active Testing

Replace the **Active Testing** stage's stub with your actual Noname / Akamai Active Testing invocation against `${TARGET_URL}/openapi.json`. Store any Active Testing credentials in **Manage Jenkins → Credentials** (never in the Jenkinsfile) and inject them with the Credentials Binding plugin.

The expected outcome for this lab: after a baseline is trained, Active Testing surfaces the **BOLA** finding on `/api/notes/{id}`. Applying the ownership-check fix in the app, then re-running, should clear it.

---

## Triggering builds automatically (optional)

Jenkins is on a private IP (`192.168.1.100`), so GitHub's cloud cannot push webhooks to it directly. Until a tunnel or port-forward is in place, builds won't auto-trigger on push. Options:

- Trigger manually (**Build Now** / **Scan Repository Now**)
- Enable periodic scanning in the Multibranch job configuration
- Expose Jenkins via a tunnel (e.g. ngrok) or port-forward, then register a GitHub webhook

---

## Quick reference

| Thing | Value |
|-------|-------|
| Jenkins URL | http://192.168.1.100:8080 |
| Credential ID | `github-token` (must match exactly in every pipeline) |
| Repo | https://github.com/mcropsey/jenkins-setup-with-sample-api-app |
| Target (VulnNotes) | http://192.168.1.98:8000 |
| Jenkinsfile location | repo root, named exactly `Jenkinsfile` |

**Things that bite people:**
- Pipeline `sh` steps run *inside the Jenkins Docker container*, not on the host — so tools and network access must exist there.
- A Multibranch Pipeline builds only branches that contain a `Jenkinsfile`.
- Keep GitHub and Noname secrets in Jenkins Credentials, never in the Jenkinsfile.
- Jenkins config and jobs persist in the `jenkins-data` Docker volume across restarts.
