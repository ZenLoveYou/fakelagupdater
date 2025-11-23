import requests
import json
import uuid
import socket
import getpass
import platform
import hashlib
import os
import sys

class AuthlyX:
    def __init__(self, owner_id, app_name, version, secret):
        self.base_url = "https://authly.cc/api/v1"
        self.session_id = None
        self.owner_id = owner_id
        self.app_name = app_name
        self.version = version
        self.secret = secret
        self.application_hash = None
        self.initialized = False
        
        self.response = {
            "success": False,
            "message": "",
            "raw": ""
        }
        
        self.user_data = {
            "username": "",
            "email": "",
            "license_key": "",
            "subscription": "",
            "expiry_date": "",
            "last_login": "",
            "hwid": "",
            "ip_address": "",
            "registered_at": ""
        }
        
        self.variable_data = {
            "var_key": "",
            "var_value": "",
            "updated_at": ""
        }
        
        if not all([owner_id, app_name, version, secret]):
            self._error("Invalid application credentials provided.")
            sys.exit(1)
            
        self._calculate_application_hash()

    def _calculate_application_hash(self):
        """Automatically calculates the application hash from the current executable file."""
        try:
            file_path = sys.executable
            
            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256()
                while chunk := f.read(8192):
                    file_hash.update(chunk)
                
                self.application_hash = file_hash.hexdigest()
                self._log(f"[HASH] Calculated application hash: {self.application_hash[:16]}...")
                
        except Exception as e:
            self._log(f"[HASH_ERROR] Failed to calculate hash: {str(e)}")
            self.application_hash = "UNKNOWN_HASH"

    def _log(self, content):
        """Logs messages to file similar to C# version"""
        try:
            if sys.platform == "win32":
                base_dir = os.path.join(os.environ.get('PROGRAMDATA', ''), "AuthlyX", "logs", self.app_name)
            else:
                base_dir = "/var/log/AuthlyX"
                
            os.makedirs(base_dir, exist_ok=True)
            
            from datetime import datetime
            log_file = os.path.join(base_dir, f"{datetime.now().strftime('%b_%d_%Y')}_log.txt")
            
            redacted = self._redact(content)
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {redacted}\n")
                
        except Exception:
            pass

    def _redact(self, text):
        """Redacts sensitive information from logs"""
        if not text:
            return text
            
        import re
        fields = ["session_id", "owner_id", "secret", "password", "key", "license_key", "hash"]
        
        for field in fields:
            pattern = f'"{field}":\\s*"[^"]*"'
            text = re.sub(pattern, f'"{field}":"REDACTED"', text, flags=re.IGNORECASE)
            
        return text

    def _error(self, message):
        """Displays error message and exits"""
        self._log(f"[ERROR] {message}")
        
        if sys.platform == "win32":
            import subprocess
            try:
                subprocess.run([
                    'cmd.exe', '/c', 'start', 'cmd', '/C', 
                    f'color 4 && title AuthlyX Error && echo {message} && timeout /t 5'
                ], shell=True, capture_output=True)
            except:
                pass
                
        print(f"AuthlyX Error: {message}")
        sys.exit(1)

    def _post_json(self, endpoint, payload):
        try:
            url = f"{self.base_url}/{endpoint}"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"AuthlyX-Python-Client/{self.version}"
            }
            
            if self.application_hash and endpoint != "init":
                payload["hash"] = self.application_hash
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            self.response["raw"] = response.text
            
            try:
                data = response.json()
            except json.JSONDecodeError:
                self.response["success"] = False
                self.response["message"] = "Invalid JSON response from server"
                return False
            
            self.response["success"] = data.get("success", False)
            self.response["message"] = data.get("message", "")
            
            if self.response["success"] and "session_id" in data:
                self.session_id = data["session_id"]
            
            self._load_user_data(data)
            self._load_variable_data(data)
            
            return self.response["success"]
            
        except requests.exceptions.RequestException as e:
            self.response["success"] = False
            self.response["message"] = f"Network error: {str(e)}"
            self._log(f"[NETWORK_ERROR] {str(e)}")
            return False
        except Exception as e:
            self.response["success"] = False
            self.response["message"] = f"Unexpected error: {str(e)}"
            self._log(f"[ERROR] {str(e)}")
            return False

    def _check_init(self):
        """Checks if AuthlyX has been initialized"""
        if not self.initialized:
            self._error("You must Initialize AuthlyX first")

    def _load_user_data(self, data):
        try:
            license_data = data.get("license", {})
            user_data = data.get("user", data.get("info", {}))
            
            if license_data:
                self.user_data["license_key"] = license_data.get("license_key", "")
                self.user_data["subscription"] = license_data.get("subscription", "")
                self.user_data["expiry_date"] = license_data.get("expiry_date", "")
                self.user_data["last_login"] = license_data.get("last_login", "")
                self.user_data["email"] = license_data.get("email", "")

            self.user_data["username"] = user_data.get("username", "")
            self.user_data["email"] = user_data.get("email", self.user_data["email"])
            self.user_data["subscription"] = user_data.get("subscription", self.user_data["subscription"])
            self.user_data["expiry_date"] = user_data.get("expiry_date", self.user_data["expiry_date"])
            self.user_data["last_login"] = user_data.get("last_login", self.user_data["last_login"])
            self.user_data["registered_at"] = user_data.get("created_at", "")
            
            self.user_data["hwid"] = self._get_system_hwid()
            self.user_data["ip_address"] = self._get_public_ip()
            
        except Exception as e:
            self._log(f"[USER_DATA_ERROR] {str(e)}")

    def _load_variable_data(self, data):
        try:
            variable = data.get("variable", {})
            self.variable_data["var_key"] = variable.get("var_key", "")
            self.variable_data["var_value"] = variable.get("var_value", "")
            self.variable_data["updated_at"] = variable.get("updated_at", "")
        except Exception as e:
            self._log(f"[VARIABLE_DATA_ERROR] {str(e)}")

    def _get_system_hwid(self):
        try:
            if sys.platform == "win32":
                import ctypes
                import ctypes.wintypes
                GetUserNameEx = ctypes.windll.secur32.GetUserNameExW
                NameDisplay = 3

                size = ctypes.wintypes.DWORD(0)
                GetUserNameEx(NameDisplay, None, ctypes.byref(size))
                if size.value:
                    buffer = ctypes.create_unicode_buffer(size.value)
                    if GetUserNameEx(NameDisplay, buffer, ctypes.byref(size)):
                        return str(uuid.uuid5(uuid.NAMESPACE_DNS, buffer.value))
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, platform.node() + getpass.getuser()))
        except:
            return "UNKNOWN_HWID"

    def _get_public_ip(self):
        """Gets public IP address like C# version"""
        try:
            response = requests.get("https://api.ipify.org", timeout=10)
            public_ip = response.text.strip()
            
            if public_ip and '.' in public_ip and len(public_ip) >= 7:
                self._log(f"[IP] Retrieved public IP: {public_ip}")
                return public_ip
        except Exception as e:
            self._log(f"[IP_ERROR] Failed to get public IP: {str(e)}")
        return "UNKNOWN_IP"

    def init(self):
        """Initializes the connection with AuthlyX"""
        try:
            payload = {
                "owner_id": self.owner_id,
                "app_name": self.app_name,
                "version": self.version,
                "secret": self.secret,
                "hash": self.application_hash
            }

            if self._post_json("init", payload):
                self.initialized = True
                self._log("[INIT] Successfully initialized AuthlyX session")
                return True
            else:
                self._error(f"Initialization failed: {self.response['message']}")
                return False
                
        except Exception as e:
            self._error(f"Initialization error: {str(e)}")
            return False

    def login(self, username, password):
        self._check_init()
            
        payload = {
            "session_id": self.session_id,
            "username": username,
            "password": password,
            "hwid": self._get_system_hwid(),
            "ip": self._get_public_ip()
        }
        return self._post_json("login", payload)

    def register(self, username, password, key, email=None):
        self._check_init()
            
        payload = {
            "session_id": self.session_id,
            "username": username,
            "password": password,
            "key": key,
            "hwid": self._get_system_hwid()
        }
        
        if email:
            payload["email"] = email
            
        return self._post_json("register", payload)

    def license_login(self, license_key):
        self._check_init()
            
        payload = {
            "session_id": self.session_id,
            "license_key": license_key,
            "hwid": self._get_system_hwid(),
            "ip": self._get_public_ip()
        }
        return self._post_json("licenses", payload)

    def get_variable(self, var_key):
        self._check_init()
            
        payload = {
            "session_id": self.session_id,
            "var_key": var_key
        }
        
        if self._post_json("variables", payload):
            return self.variable_data["var_value"]
        return ""

    def set_variable(self, var_key, var_value):
        self._check_init()
            
        payload = {
            "session_id": self.session_id,
            "var_key": var_key,
            "var_value": var_value
        }
        return self._post_json("variables/set", payload)

    def log(self, message):
        self._check_init()
            
        payload = {
            "session_id": self.session_id,
            "message": message
        }
        return self._post_json("logs", payload)

    def get_current_application_hash(self):
        return self.application_hash

    def get_session_id(self):
        return self.session_id

    def is_initialized(self):
        return self.initialized

    def get_app_name(self):
        return self.app_name