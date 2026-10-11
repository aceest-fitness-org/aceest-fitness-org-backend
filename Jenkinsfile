pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 15, unit: 'MINUTES')
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
                sh 'docker build --no-cache --target test -t $IMAGE:test-$BUILD_NUMBER .'
            }
        }

        stage('Lint') {
            steps {
                sh 'docker run --rm $IMAGE:test-$BUILD_NUMBER python -m flake8 --max-line-length=100 .'
            }
        }

        stage('Test') {
            steps {
                sh 'docker run --rm $IMAGE:test-$BUILD_NUMBER'
            }
        }

        stage('Build Release Image') {
            steps {
                sh 'docker build -t $IMAGE:$BUILD_NUMBER -t $IMAGE:latest .'
            }
        }

        stage('Smoke Test') {
            steps {
                sh '''
                    docker run -d --name smoke-$BUILD_NUMBER $IMAGE:$BUILD_NUMBER
                    for i in $(seq 1 15); do
                        if docker exec smoke-$BUILD_NUMBER python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:5000/health', timeout=3)"; then
                            echo "Health check passed"
                            exit 0
                        fi
                        sleep 2
                    done
                    echo "Health check failed"
                    docker logs smoke-$BUILD_NUMBER
                    exit 1
                '''
            }
        }
    }

    post {
        always {
            sh 'docker rm -f smoke-$BUILD_NUMBER || true'
            sh 'docker rmi $IMAGE:test-$BUILD_NUMBER || true'
        }
        success {
            echo "Build ${env.BUILD_NUMBER} passed. Image ${env.IMAGE}:${env.BUILD_NUMBER} is ready."
        }
        failure {
            echo "Build ${env.BUILD_NUMBER} failed. Check the console output above."
        }
    }
}