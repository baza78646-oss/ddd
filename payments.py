import os
import uuid
import json
import base64
import requests
from yookassa import Configuration, Payment

Configuration.account_id = os.environ.get("YOOKASSA_SHOP_ID")
Configuration.secret_key = os.environ.get("YOOKASSA_SECRET_KEY")

def create_yookassa_payment(amount: float, description: str, payload: str):
    Configuration.account_id = os.environ.get("YOOKASSA_SHOP_ID")
    Configuration.secret_key = os.environ.get("YOOKASSA_SECRET_KEY")
    idempotence_key = str(uuid.uuid4())
    payment = Payment.create({
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/" # Ideally, return back to bot
        },
        "capture": True,
        "description": description,
        "metadata": {
            "payload": payload
        }
    }, idempotence_key)

    return payment.confirmation.confirmation_url, payment.id

def check_yookassa_payment(payment_id: str):
    Configuration.account_id = os.environ.get("YOOKASSA_SHOP_ID")
    Configuration.secret_key = os.environ.get("YOOKASSA_SECRET_KEY")
    payment = Payment.find_one(payment_id)
    return payment.status == 'succeeded'

def create_cryptomus_payment(amount: float, description: str, payload: str):
    api_key = os.environ.get("CRYPTOMUS_API_KEY")
    merchant_id = os.environ.get("CRYPTOMUS_MERCHANT_ID")

    if not api_key or not merchant_id:
        raise ValueError("Cryptomus credentials are not set")

    order_id = str(uuid.uuid4())
    data = {
        "amount": f"{amount:.2f}",
        "currency": "RUB",
        "order_id": order_id,
        "url_return": "https://t.me/",
        "is_payment_multiple": False,
        "lifetime": 3600
    }

    json_data = json.dumps(data)
    sign = base64.b64encode(json_data.encode('utf-8')).decode('utf-8')
    import hashlib
    sign = hashlib.md5(f"{sign}{api_key}".encode('utf-8')).hexdigest()

    headers = {
        'merchant': merchant_id,
        'sign': sign,
        'Content-Type': 'application/json'
    }

    response = requests.post("https://api.cryptomus.com/v1/payment", json=data, headers=headers)
    response.raise_for_status()
    res_json = response.json()

    if res_json.get("state") == 0:
        result = res_json.get("result", {})
        return result.get("url"), result.get("uuid")
    else:
        raise Exception(f"Cryptomus error: {res_json}")

def check_cryptomus_payment(order_uuid: str):
    api_key = os.environ.get("CRYPTOMUS_API_KEY")
    merchant_id = os.environ.get("CRYPTOMUS_MERCHANT_ID")

    data = {
        "uuid": order_uuid
    }

    json_data = json.dumps(data)
    sign = base64.b64encode(json_data.encode('utf-8')).decode('utf-8')
    import hashlib
    sign = hashlib.md5(f"{sign}{api_key}".encode('utf-8')).hexdigest()

    headers = {
        'merchant': merchant_id,
        'sign': sign,
        'Content-Type': 'application/json'
    }

    response = requests.post("https://api.cryptomus.com/v1/payment/info", json=data, headers=headers)
    response.raise_for_status()
    res_json = response.json()

    if res_json.get("state") == 0:
        status = res_json.get("result", {}).get("status")
        return status in ["paid", "paid_over"]
    return False
