#!/usr/bin/env python3
"""
Local testing script to verify GCS access before deploying to GKE.
This helps isolate Workload Identity issues from code issues.
"""

import os
import sys
from google.cloud import storage
from google.api_core.exceptions import GoogleAPIError

def test_gcs_access(bucket_name):
    """
    Test GCS access using default credentials.
    This mimics what would happen in the pod with Workload Identity.
    """
    print(f"🔍 Testing GCS access for bucket: {bucket_name}")
    print("-" * 50)
    
    try:
        # Initialize client (should use default credentials)
        print("📦 Initializing storage client...")
        client = storage.Client()
        print("✅ Client initialized successfully")
        
        # Get bucket
        print(f"\n📁 Getting bucket: {bucket_name}")
        bucket = client.bucket(bucket_name)
        
        # Test 1: List objects
        print("\n📋 Testing list objects...")
        blobs = list(bucket.list_blobs(max_results=5))
        print(f"✅ Successfully listed objects. Found {len(blobs)} objects")
        for blob in blobs[:5]:  # Show first 5
            print(f"   - {blob.name} ({blob.size} bytes)")
        
        # Test 2: Upload a test file
        print("\n⬆️ Testing upload...")
        test_content = "This is a test file from GCS access demo"
        test_blob = bucket.blob("test-file.txt")
        test_blob.upload_from_string(test_content)
        print("✅ Successfully uploaded test-file.txt")
        
        # Test 3: Download the test file
        print("\n⬇️ Testing download...")
        downloaded = test_blob.download_as_text()
        assert downloaded == test_content, "Downloaded content doesn't match"
        print("✅ Successfully downloaded and verified test-file.txt")
        
        # Test 4: Delete the test file
        print("\n🗑️ Testing delete...")
        test_blob.delete()
        print("✅ Successfully deleted test-file.txt")
        
        # Test 5: Check bucket metadata
        print("\nℹ️ Testing bucket metadata...")
        bucket.reload()
        print(f"   Bucket: {bucket.name}")
        print(f"   Location: {bucket.location}")
        print(f"   Storage Class: {bucket.storage_class}")
        print(f"   Time Created: {bucket.time_created}")
        
        print("\n" + "=" * 50)
        print("🎉 All tests passed! GCS access is working correctly.")
        return True
        
    except GoogleAPIError as e:
        print(f"\n❌ GCS API Error: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check if bucket exists: gsutil ls gs://{bucket_name}")
        print("2. Verify IAM permissions for your service account")
        print("3. Check if Workload Identity is properly configured")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Get bucket name from environment or command line
    bucket_name = os.environ.get('GCS_BUCKET_NAME')
    if len(sys.argv) > 1:
        bucket_name = sys.argv[1]
    
    if not bucket_name:
        print("❌ Please provide a bucket name")
        print("Usage: python test_gcs.py <bucket-name>")
        print("   or: export GCS_BUCKET_NAME=<bucket-name> && python test_gcs.py")
        sys.exit(1)
    
    success = test_gcs_access(bucket_name)
    sys.exit(0 if success else 1)
