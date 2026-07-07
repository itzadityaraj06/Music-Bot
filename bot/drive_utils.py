import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


class GoogleDriveManager:
    def __init__(self):
        SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
        self.service = None

        try:
            # Check if Render environment variable exists first
            if os.getenv('GOOGLE_CREDENTIALS_JSON'):
                print("🔑 Loading Google Drive credentials from Environment Variables...")
                info = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
                creds = Credentials.from_service_account_info(info, scopes=SCOPES)
                self.service = build('drive', 'v3', credentials=creds)

            # Fallback to local file for computer testing
            elif os.path.exists('credentials.json'):
                print("📁 Loading Google Drive credentials from credentials.json file...")
                creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
                self.service = build('drive', 'v3', credentials=creds)

            else:
                print("❌ ERROR: No credentials found! Missing credentials.json and GOOGLE_CREDENTIALS_JSON.")

        except Exception as e:
            print(f"❌ ERROR: Failed to authenticate Google Drive. Details: {e}")
            self.service = None

    def list_audio_files(self, folder_id):
        if not self.service:
            return []
        try:
            # Ask Google Drive for audio files inside the specific folder
            query = (
                f"'{folder_id}' in parents "
                f"and trashed = false "
                f"and mimeType contains 'audio/'"
            )
            results = self.service.files().list(q=query, fields="files(id, name)").execute()
            return results.get('files', [])
        except Exception as e:
            print(f"Error fetching files from Drive: {e}")
            return []

    def get_or_download_track(self, file_id, file_name):
        if not self.service:
            return None, False

        # Sanitize file_name to avoid path traversal / unexpected separators
        safe_name = os.path.basename(file_name)
        file_path = os.path.join(".", safe_name)

        # If already downloaded, reuse it instead of downloading again
        if os.path.exists(file_path):
            return file_path, True

        try:
            request = self.service.files().get_media(fileId=file_id)

            with open(file_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()

            return file_path, True
        except Exception as e:
            print(f"Error downloading {file_name}: {e}")
            # Clean up partial file if download failed
            if os.path.exists(file_path):
                os.remove(file_path)
            return None, False