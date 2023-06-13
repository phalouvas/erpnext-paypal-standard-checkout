import frappe
from frappe import _

sitemap = 1


def get_context(context):
	context.body_class = "product-page"

	settings = frappe.get_cached_doc("PayPal Standard Payments Settings")
	context.client_id = settings.client_id
	context.currency = frappe.request.args.get("currency")
