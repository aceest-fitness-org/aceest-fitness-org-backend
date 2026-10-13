// Works on both Windows (bat) and Linux/macOS (sh) Jenkins agents.
def run(String cmd, boolean ignoreFailure = false) {
    if (isUnix()) {
        return sh(script: cmd, returnStatus: ignoreFailure)
    }
    return bat(script: cmd, returnStatus: ignoreFailure)
}

// Same, but returns the command's output ("@" stops cmd.exe echoing the command itself).
def runOut(String cmd) {
    if (isUnix()) {
        return sh(script: cmd, returnStdout: true).trim()
    }
    return bat(script: "@" + cmd, returnStdout: true).trim()
}

// Keep the newest `keep` release images (tags that are plain build numbers).
// Test images are removed after every build, so only release images accumulate.
def cleanupOldImages(int keep) {
    def tags = runOut("docker images ${env.IMAGE} --format \"{{.Tag}}\"")
    def current = env.BUILD_NUMBER.toInteger()
    for (String line : tags.split(/\r?\n/)) {
        def tag = line.trim()
        if (tag ==~ /\d+/ && tag.toInteger() <= current - keep) {
            echo "Removing old image ${env.IMAGE}:${tag}"
            run("docker rmi ${env.IMAGE}:${tag}", true)
        }
    }
    // Untagged leftovers from this project only (matched by the Dockerfile label)
    run("docker image prune -f --filter \"label=project=aceest-api\"", true)
}

pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 20, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    triggers {
        pollSCM('H/2 * * * *')
    }

    environment {
        IMAGE = 'aceest-api'
        KEEP_IMAGES = '3'
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
                    // Runs every tests/test_*.py, so older versions are regression-tested too
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
            script {
                // Only after a green build, so a failure never removes the last good image
                cleanupOldImages(env.KEEP_IMAGES.toInteger())
            }
            echo "Build ${env.BUILD_NUMBER} passed. Image ${env.IMAGE}:${env.BUILD_NUMBER} is ready."
        }
        failure {
            echo "Build ${env.BUILD_NUMBER} failed. Check the console output above."
        }
    }
}
