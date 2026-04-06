# Project Guidelines

## Code Style
- This is a Frappe app; follow existing Python/Frappe patterns already used in the codebase.
- Keep changes narrow and local. Avoid broad refactors unless requested.
- Preserve existing naming and request/response patterns in whitelisted API methods.

## Architecture
- The app implements a PayPal Standard gateway for ERPNext.
- Core payment flow lives in `paypalstandardpayments/paypal_standard_payments_gateway/doctype/paypal_standard_payments_settings/paypal_standard_payments_settings.py`:
  - `create_order()` creates the PayPal order and records an `Integration Request`.
  - `on_approve()` captures payment and finalizes ERPNext payment authorization.
- Checkout page context is prepared in `paypalstandardpayments/www/checkout/index.py` and rendered from `paypalstandardpayments/www/checkout/index.html`.
- Payment Entry integration is event-driven via `doc_events` in `paypalstandardpayments/hooks.py`, calling `hooks/payment_entry.py` on `Payment Entry.before_insert`.

## Build and Test
- Install in a bench environment with:
  - `bench get-app --branch=master paypalstandardpayments https://github.com/phalouvas/erpnext-paypal-standard-checkout`
- Run app tests from bench with:
  - `bench --site <site-name> run-tests --app paypalstandardpayments`
- There is currently only a placeholder test module in `.../test_paypal_standard_payments_settings.py`; add or update tests when changing payment behavior.

## Conventions
- `PayPal Standard Payments Settings` is a Single DocType and is the source of truth for gateway credentials/tokens.
- Keep PayPal API calls centralized through helper functions (`get_api_url`, `get_token`, `validate_capture`) rather than duplicating request logic.
- Maintain `Integration Request` status transitions in payment flow (`Queued`, `Authorized`, `Completed`/`Failed`) for traceability.
- When handling whitelisted endpoints, parse payloads from `frappe.request.get_data()` and write output through `frappe.local.response.update(...)`.

## Pitfalls
- Be careful when changing token expiry handling. `get_token()` relies on persisted `expire_time` and may request a new token if expired.
- `on_approve()` temporarily patches ERPNext payment entry behavior for request scope; preserve the `try/finally` restoration pattern.
- The `Payment Entry` hook expects PayPal metadata in request context; guard edge cases when modifying fee logic.

## References
- See `README.md` for installation basics and app metadata.
