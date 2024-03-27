import frappe
from frappe import _

sitemap = 1


def get_context(context):
	context.body_class = "product-page"
	context.no_cache = 1
	context.show_sidebar = 0

	settings = frappe.get_cached_doc("PayPal Standard Payments Settings")
	context.client_id = settings.client_id
	context.currency = frappe.request.args.get("currency")

	# Get reference_doctype and reference_docname from the URL
	reference_doctype = frappe.request.args.get("reference_doctype")
	reference_docname = frappe.request.args.get("reference_docname")
	context.reference_doc = frappe.get_doc(reference_doctype, reference_docname)