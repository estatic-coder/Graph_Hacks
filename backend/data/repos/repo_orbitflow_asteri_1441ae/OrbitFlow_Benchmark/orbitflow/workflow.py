from orbitflow.state import Shipment
from orbitflow.risk import evaluate_risk
from orbitflow.stock import reserve
from orbitflow.dispatch import dispatch
from orbitflow.storage import save_shipment, append_event
from orbitflow.notify import notify_customer

def submit_order(order_id, customer_id, amount, sku):
    shipment = Shipment(order_id, customer_id, amount)
    decision = evaluate_risk(customer_id, amount)
    if decision == "manual_review":
        shipment.status = "review"
        save_shipment(shipment)
        append_event(order_id, "review")
        return shipment
    if not reserve(order_id, sku):
        shipment.status = "out_of_stock"
        append_event(order_id, "out_of_stock")
        notify_customer(order_id, "out_of_stock")
        return shipment
    save_shipment(shipment)
    return dispatch(shipment, sku)
