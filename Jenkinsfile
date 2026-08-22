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
