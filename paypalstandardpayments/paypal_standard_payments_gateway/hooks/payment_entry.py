import frappe
import json

def add_invoice_fees(doc, method=None):
    if doc.doctype == "Payment Entry":
        settings = frappe.get_single("PayPal Standard Payments Settings")
        if settings.account_fees:
            fees = False
            request_data = frappe.request.get_data()
            try:
                data = json.loads(request_data)
            except json.JSONDecodeError:
                return

            orderID = data.get('orderID')
            if orderID:
                integration_request = frappe.get_doc('Integration Request', orderID)
                order = json.loads(integration_request.output)
                fees = frappe.utils.flt(order["purchase_units"][0]["payments"]["captures"][0]["seller_receivable_breakdown"]["paypal_fee"]["value"])
            elif data.get('total_commision'):
                fees = frappe.utils.flt(data.get('total_commision'))

            if fees:
                doc.append("taxes", {
                    "charge_type": "Actual",
                    "add_deduct_tax": "Add",
                    "account_head": settings.paypal_account,
                    "description": "PayPal Fees",
                    "tax_amount": fees,
                    "tax_rate": 0,
                    "cost_center": settings.cost_center
                })
                doc.append("taxes", {
                    "charge_type": "Actual",
                    "add_deduct_tax": "Deduct",
                    "account_head": settings.account_fees,
                    "description": "PayPal Fees",
                    "tax_amount": fees,
                    "tax_rate": 0,
                    "cost_center": settings.cost_center
                })
            pass