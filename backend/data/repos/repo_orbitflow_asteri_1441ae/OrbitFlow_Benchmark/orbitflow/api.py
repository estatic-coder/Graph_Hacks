from orbitflow.workflow import submit_order
from orbitflow.storage import SHIPMENTS

def create_order(payload):
    return submit_order(payload["order_id"], payload["customer_id"], payload["amount"], payload["sku"])

def get_order(order_id):
    return SHIPMENTS.get(order_id)
