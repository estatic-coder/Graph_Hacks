from orbitflow.carrier import create_label
from orbitflow.config import MAX_RETRIES
from orbitflow.stock import release
from orbitflow.storage import append_event
from orbitflow.notify import notify_customer

def dispatch(shipment, sku):
    while shipment.attempts <= MAX_RETRIES:
        shipment.attempts += 1
        try:
            create_label(shipment.order_id)
            shipment.status = "shipped"
            append_event(shipment.order_id, "shipped")
            notify_customer(shipment.order_id, "shipped")
            return shipment
        except TimeoutError:
            append_event(shipment.order_id, "carrier_retry")
    release(shipment.order_id, sku)
    shipment.status = "failed"
    append_event(shipment.order_id, "failed")
    notify_customer(shipment.order_id, "failed")
    return shipment
