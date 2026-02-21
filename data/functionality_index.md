# Functionality Index

Use this file to map product capabilities to core files.
Retrieval uses `keywords` plus listed files as semantic boosts.

## Checkout & Payment Flow
keywords: checkout,payment,invoice,billing,cart,order,failed,pending
- restaurant-portal/src/components/features/OrderCard.tsx
- restaurant-portal/src/components/features/OrderDetailsModal.tsx
- restaurant-portal/src/components/features/PaymentStatusBadge.tsx
- customer-portal/src/pages/Checkout.tsx
- backend/app/api/v1/orders.py
- backend/app/models/platform_order.py

## WhatsApp Messaging
keywords: whatsapp,message,notification,send,retry,status,webhook
- backend/app/api/webhook/whatsapp.py
- backend/app/services/whatsapp_tasks.py
- backend/app/integrations/whatsapp.py

## Order Management
keywords: order,status,prepare,kitchen,received,history
- restaurant-portal/src/pages/Orders.tsx
- restaurant-portal/src/pages/OrdersTable.tsx
- restaurant-portal/src/components/features/OrderList.tsx
- restaurant-portal/src/components/features/OrderStatusBadge.tsx

## Auth & Session
keywords: auth,login,token,session,user
- customer-portal/src/store/authStore.ts
- admin-portal/src/store/authStore.ts
- backend/app/api/v1/auth.py
