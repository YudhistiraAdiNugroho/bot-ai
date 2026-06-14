import os
import re
import json
from pathlib import Path
from firebase_memory import credentials, firestore 
import firebase_admin
from dotenv import load_dotenv
from datetime import datetime, timezone
from firebase_admin import credentials, firestore


load_dotenv("/mnt/data/hermes/telegram-bot/.env")


class FirebaseMemory:
    def __init__(self):
        self.db = None
        self.admin_ids = []
        self.MAX_MEMORY = int(os.getenv("MAX_MEMORY", "20"))
        self.SUMMARY_KEEP = int(os.getenv("SUMMARY_KEEP", "6"))

        self._init_admins()
        self._init_firebase()

    def _init_admins(self):
        raw = os.getenv("ADMIN_IDS", "")
        self.admin_ids = [x.strip() for x in raw.split(",") if x.strip()]
        print(f"👑 Admin IDs: {self.admin_ids}")

    def _init_firebase(self):
        try:
            cred_json_str = os.getenv("FIREBASE_CREDENTIALS_JSON")
            cred_path = os.getenv(
                "FIREBASE_CRED_PATH",
                "/mnt/data/hermes/telegram-bot/.env"
            )

            if cred_json_str:
                cred_dict = json.loads(cred_json_str)
                cred = credentials.Certificate(cred_dict)
            elif os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
            else:
                raise ValueError("Firebase credential tidak ditemukan di .env atau file json")

            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)

            self.db = firestore.client()
            print("✅ Firebase Firestore initialized")

        except Exception as e:
            print(f"❌ Firebase init error: {type(e).__name__}: {e}")
            raise

    def is_admin(self, user_id):
        return str(user_id) in self.admin_ids

    def _validate_user_id(self, user_id):
        user_id_str = str(user_id)

        # support normal user_id dan anonymous sender_chat id negatif
        if not re.match(r"^-?\d+$", user_id_str):
            raise ValueError(f"Invalid user_id format: {user_id}")

        return user_id_str

    def _doc_ref(self, user_id):
        return self.db.collection("chat_memories").document(
            self._validate_user_id(user_id)
        )

    def load_memory(self, user_id):
        try:
            doc = self._doc_ref(user_id).get()

            if not doc.exists:
                return []

            data = doc.to_dict() or {}
            history = data.get("history", [])

            if not isinstance(history, list):
                return []

            return history

        except Exception as e:
            print(f"[MEMORY] load error user={user_id}: {e}")
            return []

    def save_memory(self, user_id, history):
        try:
            if not isinstance(history, list):
                history = []

            if len(history) > self.MAX_MEMORY:
                history = history[-self.MAX_MEMORY:]

            self._doc_ref(user_id).set({
                "history": history,
                "user_id": str(user_id),
                "message_count": len(history),
                "last_updated": firestore.SERVER_TIMESTAMP,
            }, merge=True)

            self.db.collection("bot_stats").document("global").set({
                "total_messages": firestore.Increment(1),
                "last_active": firestore.SERVER_TIMESTAMP,
            }, merge=True)

            return True

        except Exception as e:
            print(f"[MEMORY] save error user={user_id}: {e}")
            return False

    def add_memory(self, user_id, role, content):
        try:
            if role not in {"user", "assistant", "system"}:
                print(f"[MEMORY] invalid role: {role}")
                return False

            if content is None:
                content = ""

            content = str(content)

            # jangan simpan file besar mentah ke memory chat
            content = self._compact_content(content)

            history = self.load_memory(user_id)
            history.append({
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            return self.save_memory(user_id, history)

        except Exception as e:
            print(f"[MEMORY] add error user={user_id}: {e}")
            return False

    def commit_pair(self, user_id, user_text, assistant_text):
        try:
            history = self.load_memory(user_id)

            history.append({
                "role": "user",
                "content": self._compact_content(user_text),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            history.append({
                "role": "assistant",
                "content": self._compact_content(assistant_text),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            return self.save_memory(user_id, history)

        except Exception as e:
            print(f"[MEMORY] commit_pair error user={user_id}: {e}")
            return False

    def _compact_content(self, content):
        content = str(content or "")

        if content.startswith("[ZIP PROJECT:"):
            header = content.split("\n", 1)[0]
            instruction = ""

            if "Pertanyaan lanjutan user:" in content:
                instruction = content.split("Pertanyaan lanjutan user:")[-1].strip()[:500]
            elif "Instruksi/pertanyaan user:" in content:
                instruction = content.split("Instruksi/pertanyaan user:")[-1].strip()[:500]
            else:
                instruction = "ZIP project analysis"

            return f"{header} — {instruction}"

        if content.startswith("[FILE:"):
            header = content.split("\n", 1)[0]
            instruction = ""

            if "Pertanyaan lanjutan user:" in content:
                instruction = content.split("Pertanyaan lanjutan user:")[-1].strip()[:500]
            elif "Instruksi/pertanyaan user:" in content:
                instruction = content.split("Instruksi/pertanyaan user:")[-1].strip()[:500]
            else:
                instruction = "File analysis"

            return f"{header} — {instruction}"

        max_len = 4000
        if len(content) > max_len:
            return content[:max_len] + "\n... [truncated]"

        return content

    def clear_memory(self, user_id):
        try:
            self._doc_ref(user_id).delete()
            print(f"🗑 Memory cleared user={user_id}")
            return True
        except Exception as e:
            print(f"[MEMORY] clear error user={user_id}: {e}")
            return False

    def get_memory_count(self, user_id):
        return len(self.load_memory(user_id))

    def get_memory_size(self, user_id):
        try:
            doc = self._doc_ref(user_id).get()
            if not doc.exists:
                return 0

            return len(json.dumps(doc.to_dict(), default=str, ensure_ascii=False))

        except Exception:
            return 0

    def get_all_users(self):
        try:
            docs = self.db.collection("chat_memories").stream()
            users = []

            for doc in docs:
                data = doc.to_dict() or {}
                users.append({
                    "user_id": doc.id,
                    "message_count": data.get("message_count", 0),
                    "last_updated": data.get("last_updated"),
                })

            epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

            return sorted(
                users,
                key=lambda x: x.get("last_updated") or epoch,
                reverse=True,
            )

        except Exception as e:
            print(f"[MEMORY] get_all_users error: {e}")
            return []

    def get_stats(self):
        try:
            users = self.get_all_users()
            total_messages = sum(u.get("message_count", 0) for u in users)

            return {
                "total_users": len(users),
                "total_messages": total_messages,
                "avg_messages_per_user": total_messages // max(len(users), 1),
            }

        except Exception as e:
            print(f"[MEMORY] stats error: {e}")
            return {
                "total_users": 0,
                "total_messages": 0,
                "avg_messages_per_user": 0,
            }

    def delete_user_memory(self, admin_id, target_user_id):
        if not self.is_admin(admin_id):
            print("[MEMORY] delete denied: not admin")
            return False

        return self.clear_memory(target_user_id)

    def save_file_session_meta(self, user_id, filename, mode="file"):
        try:
            self.db.collection("file_sessions_meta").document(str(user_id)).set({
                "user_id": str(user_id),
                "filename": filename,
                "mode": mode,
                "last_updated": firestore.SERVER_TIMESTAMP,
            }, merge=True)

            return True

        except Exception as e:
            print(f"[MEMORY] file session meta error: {e}")
            return False

    def get_file_session_meta(self, user_id):
        try:
            doc = self.db.collection("file_sessions_meta").document(str(user_id)).get()

            if not doc.exists:
                return None

            return doc.to_dict()

        except Exception as e:
            print(f"[MEMORY] get file session meta error: {e}")
            return None

    def clear_file_session_meta(self, user_id):
        try:
            self.db.collection("file_sessions_meta").document(str(user_id)).delete()
            return True
        except Exception as e:
            print(f"[MEMORY] clear file session meta error: {e}")
            return False