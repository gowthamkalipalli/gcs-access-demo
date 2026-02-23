import os
import logging
from flask import Flask, jsonify, request, render_template_string
from google.cloud import storage
from google.api_core.exceptions import GoogleAPIError
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Get bucket name from environment variable
BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME', 'your-bucket-name')

# HTML template for the home page
HOME_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>GCS Access Demo</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
        h1 { color: #333; }
        .container { max-width: 800px; margin: auto; }
        .card { border: 1px solid #ddd; padding: 20px; margin: 20px 0; border-radius: 5px; }
        .success { color: green; background: #e8f5e8; padding: 10px; border-radius: 3px; }
        .error { color: red; background: #ffe8e8; padding: 10px; border-radius: 3px; }
        input, button { padding: 10px; margin: 5px; }
        ul { list-style: none; padding: 0; }
        li { padding: 10px; border-bottom: 1px solid #eee; }
        .btn { background: #007bff; color: white; border: none; cursor: pointer; }
        .btn:hover { background: #0056b3; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Google Cloud Storage Access Demo</h1>
        <div class="card">
            <h2>Identity Information</h2>
            <p><strong>Service Account:</strong> {{ identity }}</p>
            <p><strong>Bucket Name:</strong> {{ bucket_name }}</p>
        </div>
        
        <div class="card">
            <h2>List Objects in Bucket</h2>
            <button onclick="location.href='/list'" class="btn">List Objects</button>
        </div>
        
        <div class="card">
            <h2>Upload File</h2>
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file" required>
                <button type="submit" class="btn">Upload</button>
            </form>
        </div>
        
        <div class="card">
            <h2>Download File</h2>
            <form action="/download" method="get">
                <input type="text" name="filename" placeholder="Enter filename" required>
                <button type="submit" class="btn">Download</button>
            </form>
        </div>
        
        <div class="card">
            <h2>Delete File</h2>
            <form action="/delete" method="post">
                <input type="text" name="filename" placeholder="Enter filename" required>
                <button type="submit" class="btn">Delete</button>
            </form>
        </div>
        
        {% if message %}
        <div class="{{ message_class }}">
            {{ message }}
        </div>
        {% endif %}
        
        {% if files %}
        <div class="card">
            <h3>Files in Bucket:</h3>
            <ul>
            {% for file in files %}
                <li>{{ file }}</li>
            {% endfor %}
            </ul>
        </div>
        {% endif %}
    </div>
</body>
</html>
'''

def get_storage_client():
    """Initialize and return a GCS client."""
    try:
        # IMPORTANT: No authentication options needed!
        # Workload Identity automatically handles authentication
        client = storage.Client()
        logger.info("Successfully created storage client")
        return client
    except Exception as e:
        logger.error(f"Failed to create storage client: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def get_identity():
    """Get the current service account identity."""
    try:
        client = storage.Client()
        # This will fail if not properly authenticated
        project = client.project
        # Try to get the email from metadata server
        import requests
        response = requests.get(
            'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email',
            headers={'Metadata-Flavor': 'Google'},
            timeout=5
        )
        if response.status_code == 200:
            return response.text
        return f"Authenticated (Project: {project})"
    except Exception as e:
        logger.error(f"Failed to get identity: {str(e)}")
        return "Unknown (Not properly authenticated)"

@app.route('/')
def home():
    """Home page."""
    return render_template_string(
        HOME_TEMPLATE,
        identity=get_identity(),
        bucket_name=BUCKET_NAME,
        message=request.args.get('message', ''),
        message_class=request.args.get('message_class', '')
    )

@app.route('/list')
def list_objects():
    """List all objects in the bucket."""
    try:
        client = get_storage_client()
        if not client:
            return render_template_string(
                HOME_TEMPLATE,
                identity=get_identity(),
                bucket_name=BUCKET_NAME,
                message="Failed to create storage client. Check Workload Identity configuration.",
                message_class="error"
            )
        
        bucket = client.bucket(BUCKET_NAME)
        blobs = list(bucket.list_blobs())
        
        files = [blob.name for blob in blobs]
        
        return render_template_string(
            HOME_TEMPLATE,
            identity=get_identity(),
            bucket_name=BUCKET_NAME,
            files=files,
            message=f"Found {len(files)} files in bucket",
            message_class="success"
        )
    except GoogleAPIError as e:
        logger.error(f"GCS API error: {str(e)}")
        return render_template_string(
            HOME_TEMPLATE,
            identity=get_identity(),
            bucket_name=BUCKET_NAME,
            message=f"GCS Error: {str(e)}",
            message_class="error"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template_string(
            HOME_TEMPLATE,
            identity=get_identity(),
            bucket_name=BUCKET_NAME,
            message=f"Error: {str(e)}",
            message_class="error"
        )

@app.route('/upload', methods=['POST'])
def upload_file():
    """Upload a file to GCS."""
    try:
        if 'file' not in request.files:
            return "No file part", 400
        
        file = request.files['file']
        if file.filename == '':
            return "No selected file", 400
        
        client = get_storage_client()
        if not client:
            return "Storage client error", 500
        
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(file.filename)
        
        # Upload the file
        blob.upload_from_file(file)
        
        logger.info(f"Successfully uploaded {file.filename}")
        return f'''
        <html>
        <body>
            <h2>Upload Successful!</h2>
            <p>File {file.filename} uploaded to {BUCKET_NAME}</p>
            <a href="/">Back to Home</a>
        </body>
        </html>
        '''
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return f"Error uploading file: {str(e)}", 500

@app.route('/download')
def download_file():
    """Download a file from GCS."""
    try:
        filename = request.args.get('filename')
        if not filename:
            return "Filename required", 400
        
        client = get_storage_client()
        if not client:
            return "Storage client error", 500
        
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        
        if not blob.exists():
            return f"File {filename} not found", 404
        
        # Download as string (for text files)
        content = blob.download_as_text()
        
        return f'''
        <html>
        <body>
            <h2>File Content: {filename}</h2>
            <pre>{content}</pre>
            <a href="/">Back to Home</a>
        </body>
        </html>
        '''
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return f"Error downloading file: {str(e)}", 500

@app.route('/delete', methods=['POST'])
def delete_file():
    """Delete a file from GCS."""
    try:
        filename = request.form.get('filename')
        if not filename:
            return "Filename required", 400
        
        client = get_storage_client()
        if not client:
            return "Storage client error", 500
        
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        
        if not blob.exists():
            return f"File {filename} not found", 404
        
        blob.delete()
        logger.info(f"Successfully deleted {filename}")
        
        return f'''
        <html>
        <body>
            <h2>Delete Successful!</h2>
            <p>File {filename} deleted from {BUCKET_NAME}</p>
            <a href="/">Back to Home</a>
        </body>
        </html>
        '''
    except Exception as e:
        logger.error(f"Delete error: {str(e)}")
        return f"Error deleting file: {str(e)}", 500

@app.route('/health')
def health():
    """Health check endpoint."""
    try:
        client = get_storage_client()
        if client:
            # Try to list buckets to verify authentication
            list(client.list_buckets(max_results=1))
            return jsonify({"status": "healthy", "authenticated": True})
        return jsonify({"status": "unhealthy", "authenticated": False}), 500
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
