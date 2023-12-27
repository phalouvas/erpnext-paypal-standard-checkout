# Copyright (c) 2023, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe

def asign_portal_user(doc, method):
    # Get logged in user
    if doc.owner == frappe.session.user:
        doc.append("portal_users", {"user": doc.owner})
        doc.save()