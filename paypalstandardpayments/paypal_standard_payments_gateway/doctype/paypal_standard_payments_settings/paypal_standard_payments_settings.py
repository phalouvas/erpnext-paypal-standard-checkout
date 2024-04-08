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
from frappe import _

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
		self.expire_time = datetime.datetime.now() - datetime.timedelta(seconds=100)
		frappe.db.set_single_value('PayPal Standard Payments Settings', 'expire_time', self.expire_time)
		self.expire_time = self.expire_time.strftime("%Y-%m-%d %H:%M:%S")
		create_payment_gateway("PayPal Standard Payments")
		call_hook_method("payment_gateway_enabled", gateway="PayPal Standard Payments")
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
	
	def validate_paypal_credentails(self):
		
		try:
			get_token(self)
		except Exception:
			frappe.throw(_("Invalid payment gateway credentials"))
	
def get_api_url(settings):
	
	if (hasattr(settings, "use_sandbox") and settings.use_sandbox):
		api_url = "https://api-m.sandbox.paypal.com"
	else:
			api_url = "https://api-m.paypal.com"

	return api_url

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
	if doc.grand_total == 0:
		doc_reference_doctype = doc.reference_doctype
		doc_reference_name = doc.reference_name
		reference_docname = frappe.get_all(reference_doctype, filters={"reference_doctype": doc_reference_doctype, "reference_name": doc_reference_name, "grand_total": (">", 0)}, fields=["name"])[0].name
		doc = frappe.get_doc(reference_doctype, reference_docname)

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
					"value": doc.grand_total,					
				},
				"description": get_description(doc),
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

def get_description(doc):
	result = doc.subject

	if doc.reference_doctype == "Sales Order":
		sales_order = frappe.get_doc("Sales Order", doc.reference_name)
		# if only one item in the cart, use the item name as description
		if len(sales_order.items) == 1:
			result = sales_order.items[0].item_name

	return result

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
		set_sales_order_status(integration_request)
		
	else:
		frappe.db.set_value('Integration Request', orderID, "status", "Failed")
		frappe.local.response.update({
			"error": "Failed to create PayPal order. Status Code: " + response.status_code
		})

	return

def set_sales_order_status(integration_request):
	# Get reference doctype
	reference_doctype = integration_request.reference_doctype
	reference_docname = integration_request.reference_docname
	doc = frappe.get_cached_doc(reference_doctype, reference_docname)
	reference_doctype = doc.reference_doctype
	if reference_doctype == "Sales Order":
		reference_name = doc.reference_name
		frappe.db.set_value(reference_doctype, reference_name, "status", "Completed")

def create_delivery_note(doc, method=None):
    is_stock_item = False
    for item in doc.items:
        is_stock_item = frappe.db.get_value("Item", item.item_code, "is_stock_item")

    if not is_stock_item:
        for item in doc.items:
            so = frappe.get_doc("Sales Order", item.sales_order)
            delivery_note = make_delivery_note(so.name)
            delivery_note.save()
            delivery_note.submit()

    pass
