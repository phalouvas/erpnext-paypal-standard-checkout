# Copyright (c) 2023, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe
from frappe.utils import call_hook_method, cint, get_datetime, get_url
from frappe.integrations.utils import create_request_log
import requests
import json
import datetime
from erpnext.accounts.doctype.payment_entry.test_payment_entry import get_payment_entry
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

from payments.utils import create_payment_gateway

class PayPalStandardPaymentsSettings(Document):

	supported_currencies = [
		"AUD",
		"BRL",
		"CAD",
		"CZK",
		"DKK",
		"EUR",
		"HKD",
		"HUF",
		"ILS",
		"JPY",
		"MYR",
		"MXN",
		"TWD",
		"NZD",
		"NOK",
		"PHP",
		"PLN",
		"GBP",
		"RUB",
		"SGD",
		"SEK",
		"CHF",
		"THB",
		"TRY",
		"USD",
	]

	def validate(self):
		create_payment_gateway("PayPal Standard Payment")
		call_hook_method("payment_gateway_enabled", gateway="PayPal Standard Payment")
		if not self.flags.ignore_mandatory:
			self.validate_paypal_credentails()

	def on_update(self):
		pass

	def validate_transaction_currency(self, currency):
		if currency not in self.supported_currencies:
			frappe.throw(
				_(
					"Please select another payment method. PayPal does not support transactions in currency '{0}'"
				).format(currency)
			)
	
	def get_payment_url(self, **kwargs):
		return_url = "/checkout?currency={0}&reference_doctype={1}&reference_docname={2}"
		return return_url.format(kwargs["currency"].upper(), kwargs['reference_doctype'], kwargs['reference_docname'])
	
def get_api_url(settings):
	
	if (hasattr(settings, "use_sandbox") and settings.use_sandbox):
		api_url = "https://api-m.sandbox.paypal.com"
	else:
			api_url = "https://api-m.paypal.com"

	return api_url

def validate_paypal_credentails(self):

		try:
			get_token(self)

		except Exception:
			frappe.throw(_("Invalid payment gateway credentials"))

def get_token(settings):

	expire_time = datetime.datetime.fromisoformat(settings.expire_time)
	if expire_time < datetime.datetime.now():
		headers = {
			"Accept": "application/json",
			"Accept-Language": "en_US"
		}
		
		data = {
			"grant_type": "client_credentials"
		}
		
		response = requests.post(get_api_url(settings) + "/v1/oauth2/token", headers=headers, data=data, auth=(settings.client_id, settings.secret_key))

		settings.token = response.json()["access_token"]
		frappe.db.set_single_value('PayPal Standard Payments Settings', 'token', settings.token)

		settings.expire_time = datetime.datetime.now() + datetime.timedelta(seconds=response.json()["expires_in"])
		frappe.db.set_single_value('PayPal Standard Payments Settings', 'expire_time', settings.expire_time)

	return settings.token

@frappe.whitelist()
def create_order():
	request_data = frappe.request.get_data()
	data = json.loads(request_data)
	reference_doctype = data["cart"][0]["reference_doctype"]
	reference_docname = data["cart"][0]["reference_docname"]
	doc = frappe.get_cached_doc(reference_doctype, reference_docname)

	settings = frappe.get_doc("PayPal Standard Payments Settings")
	get_token(settings)

	headers = {
		'Content-Type': 'application/json',
		'Authorization': 'Bearer ' + settings.token,
	}

	data = {
		"intent": "CAPTURE",
		"purchase_units": [
			{
				"reference_id": reference_docname,
				"custom_id": reference_doctype,
				"amount": {
					"currency_code": doc.currency,
					"value": doc.grand_total
				}
			}
		]
	}

	url = get_api_url(settings) + "/v2/checkout/orders"
	response = requests.post(url, headers=headers, data=json.dumps(data))

	if response.status_code == 201:
		order = response.json()
		frappe.local.response.update(order)

		intergration_request = frappe.get_doc(
			{
				"doctype": "Integration Request",
				"request_id": order["id"],
				"integration_request_service": "PayPal Checkout",
				"is_remote_request": 0,
				"request_description": "Payment Request",
				"status": "Queued",
				"url": url,
				"request_headers": json.dumps(headers),
				"data": json.dumps(data),
				"output": json.dumps(order),
				"reference_doctype": reference_doctype,
				"reference_docname": reference_docname
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value('Integration Request', intergration_request.name, "name", order["id"])
		
	else:
		frappe.local.response.update({
			"error": "Failed to create PayPal order. Status Code: " + response.status_code
		})
	
	return
	
@frappe.whitelist()
def on_approve():
	request_data = frappe.request.get_data()
	data = json.loads(request_data)
	orderID = data['orderID']
	integration_request = frappe.get_doc('Integration Request', orderID)
	frappe.db.set_value('Integration Request', orderID, "status", "Authorized")

	settings = frappe.get_doc("PayPal Standard Payments Settings")
	get_token(settings)
	
	headers = {
		'Content-Type': 'application/json',
		'Authorization': 'Bearer ' + settings.token,
	}

	url = get_api_url(settings) + "/v2/checkout/orders/" + orderID + "/capture"
	response = requests.post(url, headers=headers)

	if response.status_code == 201:
		# Set Integration request to completed
		order = response.json()
		frappe.db.set_value('Integration Request', orderID, "status", "Completed")
		frappe.db.set_value('Integration Request', orderID, "output",  json.dumps(order))

		# Create sales invoice, payment entry and response to PayPal Javascript SDK
		order["custom_redirect_to"] = frappe.get_doc(
			integration_request.reference_doctype, integration_request.reference_docname
			).run_method("on_payment_authorized", "Completed")
		frappe.db.commit()

		order["redirect_url"] = "payment-success?doctype={}&docname={}".format(
			integration_request.reference_doctype, integration_request.reference_docname
		)
		frappe.local.response.update(order)

		# Create fees invoice and payment entry
		frappe.flags.ignore_account_permission = True
		frappe.flags.ignore_permissions = True

		purchase_invoice = frappe.new_doc("Purchase Invoice")
		purchase_invoice.posting_date = frappe.utils.today()
		purchase_invoice.supplier = settings.supplier_fees
		fees = frappe.utils.flt(order["purchase_units"][0]["payments"]["captures"][0]["seller_receivable_breakdown"]["paypal_fee"]["value"])
		purchase_invoice.append(
			"items",
			{
				"item_code": settings.item_fees,
				"qty": 1,
				"rate": fees,
				"expense_account": settings.account_fees,
			},
		)
		purchase_invoice.insert(ignore_permissions=True)
		purchase_invoice.submit()

		payment_entry = get_payment_entry("Purchase Invoice", purchase_invoice.name)
		payment_entry.reference_no = orderID
		payment_entry.reference_date = purchase_invoice.posting_date
		payment_entry.paid_from_account_currency = purchase_invoice.currency
		payment_entry.paid_to_account_currency = purchase_invoice.currency
		payment_entry.source_exchange_rate = 1
		payment_entry.target_exchange_rate = 1
		payment_entry.paid_amount = purchase_invoice.grand_total
		payment_entry.save(ignore_permissions=True)
		payment_entry.submit()
		
	else:
		frappe.db.set_value('Integration Request', orderID, "status", "Failed")
		frappe.local.response.update({
			"error": "Failed to create PayPal order. Status Code: " + response.status_code
		})

	return
