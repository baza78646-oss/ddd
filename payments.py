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


def create_cryptocloud_payment(amount: float, description: str, payload: str):
    api_key = os.environ.get("CRYPTOCLOUD_API_KEY")
    shop_id = os.environ.get("CRYPTOCLOUD_SHOP_ID")

    if not api_key or not shop_id:
        raise ValueError("CryptoCloud credentials are not set")

    headers = {
        'Authorization': f'Token {api_key}',
        'Content-Type': 'application/json'
    }

    # We will pass the payload as order_id or in add_fields, order_id is a good choice to store our custom payload.
    # We should ensure amount is passed as float and shop_id is passed.
    data = {
        "amount": float(amount),
        "shop_id": shop_id,
        "currency": "RUB",
        "order_id": payload
    }

    response = requests.post("https://api.cryptocloud.plus/v2/invoice/create", json=data, headers=headers)
    response.raise_for_status()
    res_json = response.json()

    if res_json.get("status") == "success":
        result = res_json.get("result", {})
        return result.get("link"), result.get("uuid")
    else:
        raise Exception(f"CryptoCloud error: {res_json}")

def check_cryptocloud_payment(invoice_uuid: str):
    api_key = os.environ.get("CRYPTOCLOUD_API_KEY")

    headers = {
        'Authorization': f'Token {api_key}',
        'Content-Type': 'application/json'
    }

    data = {
        "uuids": [invoice_uuid]
    }

    response = requests.post("https://api.cryptocloud.plus/v2/invoice/merchant/info", json=data, headers=headers)
    response.raise_for_status()
    res_json = response.json()

    if res_json.get("status") == "success":
        results = res_json.get("result", [])
        if results:
            status = results[0].get("status")
            return status in ["paid", "overpaid"]
    return False
