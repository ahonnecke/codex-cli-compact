# 10-Query Quality Leaderboard

- token_provider: `heuristic`
- real_output: `False`
- model: `gpt-5-mini`
- avg_token_reduction: **88.1%**
- avg_quality_delta: **23.4**

| # | Query | Baseline Tokens | Graph Tokens | Reduction | Baseline Q | Graph Q | Delta |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | fix checkout pricing flow bug when invoice fails | 7974 | 780 | 90.2% | 36.7 | 70.8 | 34.2 |
| 2 | update whatsapp feature so it can generate invoice pdf | 7975 | 1095 | 86.3% | 51.2 | 15.0 | -36.2 |
| 3 | improve customer portal cart checkout state handling | 7975 | 976 | 87.8% | 25.0 | 69.6 | 44.6 |
| 4 | add retry logic for whatsapp send failures | 7972 | 927 | 88.4% | 45.4 | 50.4 | 5.0 |
| 5 | fix order API response mismatch for invoice endpoint | 7975 | 927 | 88.4% | 45.4 | 70.8 | 25.4 |
| 6 | audit authentication checks in checkout submission flow | 7975 | 797 | 90.0% | 25.0 | 20.0 | -5.0 |
| 7 | reduce duplicate calls in customer checkout query hooks | 7975 | 962 | 87.9% | 25.0 | 30.0 | 5.0 |
| 8 | ensure restaurant location update does not break billing flow | 7977 | 1167 | 85.4% | 25.0 | 65.0 | 40.0 |
| 9 | add logging around invoice creation and webhook status | 7975 | 892 | 88.8% | 36.7 | 82.5 | 45.8 |
| 10 | patch checkout page to show clear error for payment failure | 7976 | 970 | 87.8% | 25.0 | 100.0 | 75.0 |

## Side-by-Side Outputs

### Q1. fix checkout pricing flow bug when invoice fails

**Baseline (codex_mimic)**

```text
Plan:
- Review backend/migrate_order_fields.py
- Review backend/migrate_add_is_open.py
- Review backend/add_accepting_orders.py
- Review backend/test_whatsapp.py
- Review backend/check_twilio_setup.py
- Review backend/gunicorn.conf.py
- Review backend/add_coordinates.py
- Review backend/diagnose_customer_data.py
- Review backend/setup_db.py
- Review backend/migrate_rest_db.py
- Review backend/railway.json
- Review backend/app/config.py
- Review backend/app/database.py
- Review backend/app/main.py
- Review backend/app/websocket.py
- Review backend/app/core/config.py
- Review backend/app/core/security.py
- Review backend/app/core/__init__.py
```

**Info Graph**

```text
Plan:
- Update backend/app/utils/invoice_generator.py
- Update customer-portal/src/pages/Checkout.tsx
- Update IMPLEMENTATION_PLAN.md --references--> backend/app/utils/invoice_generator.py
- Update ROOT_FIX_SUMMARY.md --references--> backend/app/api/v1/orders.py
- Update WHATSAPP_DEBUG_NEXT_STEPS.md --references--> backend/app/api/customer/orders.py
- Update WHATSAPP_FLOW_ANALYSIS.md --references--> backend/app/api/webhook/whatsapp.py
- Update backend/app/utils/invoice_generator.py --imports--> datetime
- Update backend/app/utils/invoice_generator.py --imports--> io
```

### Q2. update whatsapp feature so it can generate invoice pdf

**Baseline (codex_mimic)**

```text
Plan:
- Review backend/migrate_order_fields.py
- Review backend/migrate_add_is_open.py
- Review backend/add_accepting_orders.py
- Review backend/test_whatsapp.py
- Review backend/check_twilio_setup.py
- Review backend/gunicorn.conf.py
- Review backend/add_coordinates.py
- Review backend/diagnose_customer_data.py
- Review backend/setup_db.py
- Review backend/migrate_rest_db.py
- Review backend/railway.json
- Review backend/app/config.py
- Review backend/app/database.py
- Review backend/app/main.py
- Review backend/app/websocket.py
- Review backend/app/core/config.py
- Review backend/app/core/security.py
- Review backend/app/core/__init__.py
```

**Info Graph**

```text
Plan:
- Update restaurant-portal/src/components/features/MenuItemCard.tsx
- Update restaurant-portal/src/components/features/MenuItemForm.tsx
- Update restaurant-portal/src/components/features/MenuScanner.tsx
- Update admin-portal/package-lock.json
- Update admin-portal/package.json
- Update admin-portal/src/pages/Withdrawals.tsx
- Update admin-portal/src/vite-env.d.ts
- Update admin-portal/tsconfig.json
```

### Q3. improve customer portal cart checkout state handling

**Baseline (codex_mimic)**

```text
Plan:
- Review backend/migrate_order_fields.py
- Review backend/migrate_add_is_open.py
- Review backend/add_accepting_orders.py
- Review backend/test_whatsapp.py
- Review backend/check_twilio_setup.py
- Review backend/gunicorn.conf.py
- Review backend/add_coordinates.py
- Review backend/diagnose_customer_data.py
- Review backend/setup_db.py
- Review backend/migrate_rest_db.py
- Review backend/railway.json
- Review backend/app/config.py
- Review backend/app/database.py
- Review backend/app/main.py
- Review backend/app/websocket.py
- Review backend/app/core/config.py
- Review backend/app/core/security.py
- Review backend/app/core/__init__.py
```

**Info Graph**

```text
Plan:
- Update customer-portal/src/components/cart/CartDrawer.tsx
- Update customer-portal/src/components/ui/EmptyState.tsx
- Update customer-portal/src/pages/Cart.tsx
- Update customer-portal/src/pages/Checkout.tsx
- Update customer-portal/src/store/cartStore.ts
- Update customer-portal/package-lock.json
- Update customer-portal/package.json
- Update customer-portal/postcss.config.js
```

### Q4. add retry logic for whatsapp send failures

**Baseline (codex_mimic)**

```text
Plan:
- Review backend/migrate_order_fields.py
- Review backend/migrate_add_is_open.py
- Review backend/add_accepting_orders.py
- Review backend/test_whatsapp.py
- Review backend/check_twilio_setup.py
- Review backend/gunicorn.conf.py
- Review backend/add_coordinates.py
- Review backend/diagnose_customer_data.py
- Review backend/setup_db.py
- Review backend/migrate_rest_db.py
- Review backend/railway.json
- Review backend/app/config.py
- Review backend/app/database.py
- Review backend/app/main.py
- Review backend/app/websocket.py
- Review backend/app/core/config.py
- Review backend/app/core/security.py
- Review backend/app/core/__init__.py
```

**Info Graph**

```text
Plan:
- Update backend/app/models/platform_customer_address.py
- Update backend/app/schemas/platform_address.py
- Update backend/add_accepting_orders.py
- Update backend/add_coordinates.py
- Update backend/app/api/customer/addresses.py
- Update backend/app/api/webhook/whatsapp.py
- Update backend/app/integrations/whatsapp.py
- Update backend/app/models/platform_customer.py
```

### Q5. fix order API response mismatch for invoice endpoint

**Baseline (codex_mimic)**

```text
Plan:
- Review backend/migrate_order_fields.py
- Review backend/migrate_add_is_open.py
- Review backend/add_accepting_orders.py
- Review backend/test_whatsapp.py
- Review backend/check_twilio_setup.py
- Review backend/gunicorn.conf.py
- Review backend/add_coordinates.py
- Review backend/diagnose_customer_data.py
- Review backend/setup_db.py
- Review backend/migrate_rest_db.py
- Review backend/railway.json
- Review backend/app/config.py
- Review backend/app/database.py
- Review backend/app/main.py
- Review backend/app/websocket.py
- Review backend/app/core/config.py
- Review backend/app/core/security.py
- Review backend/app/core/__init__.py
```

**Info Graph**

```text
Plan:
- Update backend/app/api/customer/orders.py
- Update backend/app/api/v1/orders.py
- Update backend/app/models/platform_order.py
- Update backend/app/models/platform_order_item.py
- Update backend/app/schemas/platform_order.py
- Update admin-portal/src/services/api.ts
- Update backend/add_accepting_orders.py
- Update backend/app/api/__init__.py
```

### Q6. audit authentication checks in checkout submission flow

**Baseline (codex_mimic)**

```text
Plan:
- Review backend/migrate_order_fields.py
- Review backend/migrate_add_is_open.py
- Review backend/add_accepting_orders.py
- Review backend/test_whatsapp.py
- Review backend/check_twilio_setup.py
- Review backend/gunicorn.conf.py
- Review backend/add_coordinates.py
- Review backend/diagnose_customer_data.py
- Review backend/setup_db.py
- Review backend/migrate_rest_db.py
- Review backend/railway.json
- Review backend/app/config.py
- Review backend/app/database.py
- Review backend/app/main.py
- Review backend/app/websocket.py
- Review backend/app/core/config.py
- Review backend/app/core/security.py
- Review backend/app/core/__init__.py
```

**Info Graph**

```text
Plan:
- Update admin-portal/package-lock.json
- Update admin-portal/package.json
- Update admin-portal/postcss.config.js
- Update admin-portal/src/App.tsx
- Update admin-portal/src/components/layout/Sidebar.tsx
- Update admin-portal/src/main.tsx
- Update admin-portal/src/pages/Dashboard.tsx
- Update admin-portal/src/pages/Login.tsx
```

### Q7. reduce duplicate calls in customer checkout query hooks

**Baseline (codex_mimic)**

```text
Plan:
- Review backend/migrate_order_fields.py
- Review backend/migrate_add_is_open.py
- Review backend/add_accepting_orders.py
- Review backend/test_whatsapp.py
- Review backend/check_twilio_setup.py
- Review backend/gunicorn.conf.py
- Review backend/add_coordinates.py
- Review backend/diagnose_customer_data.py
- Review backend/setup_db.py
- Review backend/migrate_rest_db.py
- Review backend/railway.json
- Review backend/app/config.py
- Review backend/app/database.py
- Review backend/app/main.py
- Review backend/app/websocket.py
- Review backend/app/core/config.py
- Review backend/app/core/security.py
- Review backend/app/core/__init__.py
```

**Info Graph**

```text
Plan:
- Update backend/app/api/customer/__init__.py
- Update customer-portal/src/components/LoginModal.tsx
- Update customer-portal/src/components/ui/Input.tsx
- Update customer-portal/src/components/ui/Loading.tsx
- Update customer-portal/src/components/ui/Spinner.tsx
- Update customer-portal/src/hooks/useDebounce.ts
- Update customer-portal/src/hooks/useGeolocation.ts
- Update customer-portal/src/hooks/useLocalStorage.ts
```

### Q8. ensure restaurant location update does not break billing flow

**Baseline (codex_mimic)**

```text
Plan:
- Review backend/migrate_order_fields.py
- Review backend/migrate_add_is_open.py
- Review backend/add_accepting_orders.py
- Review backend/test_whatsapp.py
- Review backend/check_twilio_setup.py
- Review backend/gunicorn.conf.py
- Review backend/add_coordinates.py
- Review backend/diagnose_customer_data.py
- Review backend/setup_db.py
- Review backend/migrate_rest_db.py
- Review backend/railway.json
- Review backend/app/config.py
- Review backend/app/database.py
- Review backend/app/main.py
- Review backend/app/websocket.py
- Review backend/app/core/config.py
- Review backend/app/core/security.py
- Review backend/app/core/__init__.py
```

**Info Graph**

```text
Plan:
- Update restaurant-portal/src/pages/RestauranLocationUpdate.tsx
- Update backend/app/api/restaurant/location.py
- Update restaurant-portal/src/components/features/LocationPicker.tsx
- Update restaurant-portal/src/components/features/NotificationDropdown.tsx
- Update restaurant-portal/src/components/features/RestaurantLocationPicker.tsx
- Update restaurant-portal/src/components/features/SimpleLocationPicker.tsx
- Update restaurant-portal/src/pages/RestaurantLocation.tsx
- Update restaurant-portal/src/store/notificationStore.ts
```

### Q9. add logging around invoice creation and webhook status

**Baseline (codex_mimic)**

```text
Plan:
- Review backend/migrate_order_fields.py
- Review backend/migrate_add_is_open.py
- Review backend/add_accepting_orders.py
- Review backend/test_whatsapp.py
- Review backend/check_twilio_setup.py
- Review backend/gunicorn.conf.py
- Review backend/add_coordinates.py
- Review backend/diagnose_customer_data.py
- Review backend/setup_db.py
- Review backend/migrate_rest_db.py
- Review backend/railway.json
- Review backend/app/config.py
- Review backend/app/database.py
- Review backend/app/main.py
- Review backend/app/websocket.py
- Review backend/app/core/config.py
- Review backend/app/core/security.py
- Review backend/app/core/__init__.py
```

**Info Graph**

```text
Plan:
- Update backend/add_accepting_orders.py
- Update backend/add_coordinates.py
- Update backend/app/api/customer/addresses.py
- Update backend/app/api/webhook/__init__.py
- Update backend/app/api/webhook/whatsapp.py
- Update backend/app/models/platform_customer_address.py
- Update backend/app/schemas/platform_address.py
- Update backend/app/utils/invoice_generator.py
```

### Q10. patch checkout page to show clear error for payment failure

**Baseline (codex_mimic)**

```text
Plan:
- Review backend/migrate_order_fields.py
- Review backend/migrate_add_is_open.py
- Review backend/add_accepting_orders.py
- Review backend/test_whatsapp.py
- Review backend/check_twilio_setup.py
- Review backend/gunicorn.conf.py
- Review backend/add_coordinates.py
- Review backend/diagnose_customer_data.py
- Review backend/setup_db.py
- Review backend/migrate_rest_db.py
- Review backend/railway.json
- Review backend/app/config.py
- Review backend/app/database.py
- Review backend/app/main.py
- Review backend/app/websocket.py
- Review backend/app/core/config.py
- Review backend/app/core/security.py
- Review backend/app/core/__init__.py
```

**Info Graph**

```text
Plan:
- Update customer-portal/src/pages/Checkout.tsx
- Update backend/app/api/customer/payments.py
- Update backend/app/models/platform_customer.py
- Update backend/app/models/platform_customer_address.py
- Update backend/app/models/platform_customer_favorite.py
- Update backend/app/schemas/platform_customer.py
- Update customer-portal/src/components/ui/ErrorMessage.tsx
- Update customer-portal/src/pages/Addresses.tsx
```
