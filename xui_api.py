import requests
import logging
import json
import uuid

logger = logging.getLogger(__name__)

class XUIClient:
    def __init__(self, panel_url: str, username: str, password: str):
        self.panel_url = panel_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.login()

    def login(self):
        url = f"{self.panel_url}/login"
        data = {"username": self.username, "password": self.password}
        try:
            response = self.session.post(url, data=data, timeout=10)
            response.raise_for_status()
            res_data = response.json()
            if res_data.get("success"):
                logger.info(f"Successfully logged into {self.panel_url}")
            else:
                logger.error(f"Login failed for {self.panel_url}: {res_data.get('msg')}")
        except Exception as e:
            logger.error(f"Exception during login to {self.panel_url}: {e}")

    def get_inbounds(self):
        url = f"{self.panel_url}/panel/api/inbounds/list"
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            res_data = response.json()
            if res_data.get("success"):
                return res_data.get("obj", [])
            else:
                logger.error(f"Failed to get inbounds from {self.panel_url}: {res_data.get('msg')}")
                return []
        except Exception as e:
            logger.error(f"Exception getting inbounds from {self.panel_url}: {e}")
            return []

    def add_client(self, inbound_id: int, client_email: str, sub_id: str, client_uuid: str = None, expiry_time: int = 0):
        """
        Adds a new client to a specific inbound.
        Requires the subId to be passed down so that it aligns across servers.
        """
        url = f"{self.panel_url}/panel/api/inbounds/addClient"
        if not client_uuid:
            client_uuid = str(uuid.uuid4())

        # The payload format depends on the specific inbound type. We assume VLESS/VMESS.
        settings = {
            "clients": [
                {
                    "id": client_uuid,
                    "alterId": 0,
                    "email": client_email,
                    "limitIp": 0,
                    "totalGB": 0,
                    "expiryTime": expiry_time,
                    "enable": True,
                    "tgId": "",
                    "subId": sub_id
                }
            ]
        }

        data = {
            "id": inbound_id,
            "settings": json.dumps(settings)
        }

        try:
            response = self.session.post(url, data=data, timeout=10)
            response.raise_for_status()
            res_data = response.json()
            if res_data.get("success"):
                logger.info(f"Successfully added client {client_email} to {self.panel_url}")
                return True
            else:
                logger.error(f"Failed to add client to {self.panel_url}: {res_data.get('msg')}")
                return False
        except Exception as e:
            logger.error(f"Exception adding client to {self.panel_url}: {e}")
            return False

    def update_client(self, client_uuid: str, inbound_id: int, client_email: str, sub_id: str, expiry_time: int):
        """
        Updates an existing client's settings.
        """
        url = f"{self.panel_url}/panel/api/inbounds/updateClient/{client_uuid}"

        settings = {
            "clients": [
                {
                    "id": client_uuid,
                    "alterId": 0,
                    "email": client_email,
                    "limitIp": 0,
                    "totalGB": 0,
                    "expiryTime": expiry_time,
                    "enable": True,
                    "tgId": "",
                    "subId": sub_id
                }
            ]
        }

        data = {
            "id": inbound_id,
            "settings": json.dumps(settings)
        }

        try:
            response = self.session.post(url, data=data, timeout=10)
            response.raise_for_status()
            res_data = response.json()
            if res_data.get("success"):
                logger.info(f"Successfully updated client {client_email} on {self.panel_url}")
                return True
            else:
                logger.error(f"Failed to update client on {self.panel_url}: {res_data.get('msg')}")
                return False
        except Exception as e:
            logger.error(f"Exception updating client on {self.panel_url}: {e}")
            return False
