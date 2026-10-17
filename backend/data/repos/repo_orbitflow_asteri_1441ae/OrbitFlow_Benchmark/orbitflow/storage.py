SHIPMENTS = {}
EVENTS = []

def save_shipment(shipment):
    SHIPMENTS[shipment.order_id] = shipment
    return shipment

def append_event(order_id, event):
    EVENTS.append((order_id, event))
