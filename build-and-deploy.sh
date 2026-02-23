#!/bin/bash

# Exit on error
set -e

# Configuration - UPDATE THESE VALUES
export PROJECT_ID="your-gcp-project-id"
export CLUSTER_NAME="your-gke-cluster-name"
export CLUSTER_LOCATION="your-cluster-region"
export NAMESPACE="default"
export BUCKET_NAME="your-bucket-name"
export IMAGE_NAME="gcs-access-demo"
export IMAGE_TAG="latest"
export GSA_NAME="gcs-access-sa"
export KSA_NAME="my-pod-sa"

# Full image path
export IMAGE_PATH="gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "🚀 Starting deployment process..."

# Step 1: Build the Docker image
echo "📦 Building Docker image..."
docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .

# Step 2: Tag the image for Google Container Registry
echo "🏷️ Tagging image for GCR..."
docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${IMAGE_PATH}

# Step 3: Push to Google Container Registry
echo "⬆️ Pushing image to GCR..."
docker push ${IMAGE_PATH}

# Step 4: Configure kubectl
echo "🔧 Configuring kubectl..."
gcloud container clusters get-credentials ${CLUSTER_NAME} --zone=${CLUSTER_LOCATION} --project=${PROJECT_ID}

# Step 5: Create namespace if it doesn't exist
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# Step 6: Create GSA and setup permissions (if not exists)
echo "🔑 Setting up service accounts..."

# Check if GSA exists
if ! gcloud iam service-accounts describe ${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com --project=${PROJECT_ID} &>/dev/null; then
    echo "Creating Google Service Account..."
    gcloud iam service-accounts create ${GSA_NAME} \
        --project=${PROJECT_ID} \
        --display-name="GCS Access Service Account"
fi

export GSA_EMAIL="${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant bucket permissions
echo "📝 Granting bucket permissions..."
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
    --member="serviceAccount:${GSA_EMAIL}" \
    --role="roles/storage.objectAdmin"

# Step 7: Create Kubernetes service account
echo "🔧 Creating Kubernetes service account..."
kubectl create serviceaccount ${KSA_NAME} -n ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# Step 8: Allow KSA to impersonate GSA
echo "🔗 Creating IAM policy binding..."
gcloud iam service-accounts add-iam-policy-binding ${GSA_EMAIL} \
    --project=${PROJECT_ID} \
    --role="roles/iam.workloadIdentityUser" \
    --member="serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/${KSA_NAME}]"

# Step 9: Annotate KSA
echo "📝 Annotating Kubernetes service account..."
kubectl annotate serviceaccount ${KSA_NAME} \
    -n ${NAMESPACE} \
    iam.gke.io/gcp-service-account=${GSA_EMAIL} \
    --overwrite

# Step 10: Update deployment with image name
echo "📄 Updating deployment configuration..."
sed -i "s|image: .*|image: ${IMAGE_PATH}|g" k8s/deployment.yaml
sed -i "s|value: .*|value: \"${BUCKET_NAME}\"|g" k8s/deployment.yaml

# Step 11: Deploy to Kubernetes
echo "🚀 Deploying to Kubernetes..."
kubectl apply -f k8s/deployment.yaml -n ${NAMESPACE}

# Step 12: Wait for deployment to be ready
echo "⏳ Waiting for deployment to be ready..."
kubectl rollout status deployment/gcs-access-demo -n ${NAMESPACE} --timeout=300s

# Step 13: Get the service endpoint
echo "✅ Deployment complete!"
echo "📡 Service endpoint:"
kubectl get service gcs-access-demo -n ${NAMESPACE} -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
echo ""

# Step 14: Verify Workload Identity
echo "🔍 Verifying Workload Identity..."
POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app=gcs-access-demo -o jsonpath='{.items[0].metadata.name}')
echo "Checking pod: ${POD_NAME}"

# Wait a moment for the pod to be ready
sleep 10

# Check the identity
echo "Service account in use:"
kubectl exec -it ${POD_NAME} -n ${NAMESPACE} -- curl -s -H "Metadata-Flavor: Google" \
    http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email

echo ""
echo "🎉 All done! Access your application at the IP address above."
