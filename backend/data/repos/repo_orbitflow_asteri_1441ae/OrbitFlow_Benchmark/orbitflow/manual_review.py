from orbitflow.storage import SHIPMENTS, append_event
from orbitflow.stock import reserve
from orbitflow.dispatch import dispatch

def approve_review(order_id, sku):
    shipment = SHIPMENTS[order_id]
    if shipment.status != "review":
        raise ValueError("not in review")
    if not reserve(order_id, sku):
        shipment.status = "out_of_stock"
        append_event(order_id, "review_stock_failure")
        return shipment
    append_event(order_id, "review_approved")
    return dispatch(shipment, sku)
