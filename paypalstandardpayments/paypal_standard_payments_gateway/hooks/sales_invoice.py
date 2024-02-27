import frappe
import json

def add_invoice_fees(doc, method=None):
    if doc.doctype == "Sales Invoice":
        settings = frappe.get_single("PayPal Standard Payments Settings")
        if settings.account_fees:
            request_data = frappe.request.get_data()
            data = json.loads(request_data)
            orderID = data['orderID']
            integration_request = frappe.get_doc('Integration Request', orderID)
            order = json.loads(integration_request.output)
            fees = frappe.utils.flt(order["purchase_units"][0]["payments"]["captures"][0]["seller_receivable_breakdown"]["paypal_fee"]["value"])
            if fees:
                doc.append("taxes", {
                    "charge_type": "Actual",
                    "account_head": settings.paypal_account,
                    "description": "PayPal Fees",
                    "tax_amount": fees,
                    "tax_rate": 0,
                    "cost_center": settings.cost_center
                })
                doc.append("taxes", {
                    "charge_type": "Actual",
                    "account_head": settings.account_fees,
                    "description": "PayPal Fees",
                    "tax_amount": -fees,
                    "tax_rate": 0,
                    "cost_center": settings.cost_center
                })
            pass