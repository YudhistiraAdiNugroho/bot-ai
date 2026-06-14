from firebase_admin import storage
import os
import uuid
from datetime import datetime, timedelta
import mimetypes

class FirebaseUploader:
    def __init__(self):
        """Inisialisasi Firebase Storage"""
        try:
            self.bucket = storage.bucket()
            print("✅ Firebase Storage initialized")
        except Exception as e:
            print(f"❌ Storage init error: {e}")
            raise
    
    def upload_file(self, file_path, original_filename, user_id):
        """
        Upload file ke Firebase Storage
        Returns: public_url dari file yang sudah diupload
        """
        try:
            # Generate unique filename untuk avoid collision
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_id = uuid.uuid4().hex[:8]
            ext = original_filename.split('.')[-1] if '.' in original_filename else 'bin'
            
            # Path di storage: uploads/user_id/tanggal/filename
            storage_path = f"uploads/{user_id}/{datetime.now().strftime('%Y/%m/%d')}/{timestamp}_{unique_id}.{ext}"
            
            # Upload file
            blob = self.bucket.blob(storage_path)
            blob.upload_from_filename(file_path)
            
            # Set metadata
            blob.metadata = {
                'original_name': original_filename,
                'user_id': str(user_id),
                'uploaded_at': datetime.now().isoformat(),
                'size_bytes': str(os.path.getsize(file_path))
            }
            blob.patch()
            
            # Buat file public readable (opsional)
            blob.make_public()
            
            # Hapus file lokal setelah sukses upload
            os.remove(file_path)
            
            return blob.public_url
            
        except Exception as e:
            print(f"Error uploading file: {e}")
            # Jangan hapus file lokal kalau gagal upload
            return None
    
    def delete_expired_files(self, days=7):
        """
        Hapus file yang sudah lebih dari X hari
        Panggil fungsi ini via cron/scheduler
        """
        cutoff = datetime.now() - timedelta(days=days)
        deleted_count = 0
        
        try:
            # List semua file di folder uploads/
            blobs = self.bucket.list_blobs(prefix='uploads/')
            
            for blob in blobs:
                # Cek waktu upload dari metadata atau creation time
                upload_time = blob.time_created
                
                if upload_time < cutoff:
                    blob.delete()
                    deleted_count += 1
                    print(f"Deleted expired: {blob.name}")
            
            print(f"Cleanup completed: {deleted_count} files deleted")
            return deleted_count
            
        except Exception as e:
            print(f"Cleanup error: {e}")
            return 0
    
    def get_storage_usage(self):
        """Dapatkan total usage storage (bytes)"""
        total_bytes = 0
        blobs = self.bucket.list_blobs()
        for blob in blobs:
            total_bytes += blob.size
        return total_bytes

# Instance global
firebase_uploader = FirebaseUploader()
