// Works on both Windows (bat) and Linux/macOS (sh) Jenkins agents.
def run(String cmd, boolean ignoreFailure = false) {
    if (isUnix()) {
        return sh(script: cmd, returnStatus: ignoreFailure)
    }
    return bat(script: cmd, returnStatus: ignoreFailure)
}

pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 20, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    triggers {
        pollSCM('H/5 * * * *')
    }

    environment {
        IMAGE = 'aceest-api'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Clean Build') {
            steps {
                // --no-cache forces a from-scratch build of the environment
                script {
                    run("docker build --no-cache --target test -t ${env.IMAGE}:test-${env.BUILD_NUMBER} .")
                }
            }
        }

        stage('Lint') {
            steps {
                script {
                    run("docker run --rm ${env.IMAGE}:test-${env.BUILD_NUMBER} python -m flake8 --max-line-length=100 .")
                }
            }
        }

        stage('Test') {
            steps {
                script {
                    run("docker run --rm ${env.IMAGE}:test-${env.BUILD_NUMBER}")
                }
            }
        }

        stage('Build Release Image') {
            steps {
                script {
                    run("docker build -t ${env.IMAGE}:${env.BUILD_NUMBER} -t ${env.IMAGE}:latest .")
                }
            }
        }

        stage('Smoke Test') {
            steps {
                script {
                    run("docker run --rm ${env.IMAGE}:${env.BUILD_NUMBER} python -c \"from app_v1_1 import create_app; c = create_app().test_client(); assert c.get('/health').status_code == 200\"")
                }
            }
        }
    }

    post {
        always {
            script {
                run("docker rmi ${env.IMAGE}:test-${env.BUILD_NUMBER}", true)
            }
        }
        success {
            echo "Build ${env.BUILD_NUMBER} passed. Image ${env.IMAGE}:${env.BUILD_NUMBER} is ready."
        }
        failure {
            echo "Build ${env.BUILD_NUMBER} failed. Check the console output above."
        }
    }
}