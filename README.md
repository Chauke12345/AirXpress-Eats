# AirXpress Eats

AirXpress Eats is a multi-tenant Django-based online food ordering and delivery platform developed by EdVance Tech (Pty) Ltd.

## Features

### Customer Ordering
- Browse participating food businesses
- View menus and available items
- Add items to the cart
- Enter customer name and WhatsApp/contact number
- Add special instructions
- Review the complete order before payment
- Receive an order reference

### Returning Customers
AirXpress Eats remembers returning customers using their name and WhatsApp/contact number.

When the same customer returns, their most recent delivery address can automatically be restored.

Customers can change their address whenever necessary.

### Address & Delivery
AirXpress Eats uses Mapbox for address search, address verification and driving-distance calculations.

Customers can:
- Type their delivery address
- Receive Mapbox address suggestions
- Select a suggested address
- Verify the address
- Calculate the driving distance
- Receive the correct delivery fee

### Delivery Pricing

| Distance | Delivery Fee |
|---|---:|
| 0 – 2.5 km | R85 |
| 2.5 – 5 km | R105 |
| 5 – 7.5 km | R115 |
| 7.5 – 10 km | R125 |
| 10 – 12 km | R135 |
| Over 12 km | Not available |

The maximum delivery radius is 12 km.

### AirXpress Platform Fee
AirXpress applies a 15% platform fee on the food subtotal.

### Driver Payments
Driver payout is calculated internally as 40% of the delivery fee.

### PayFast Payments
AirXpress Eats integrates with PayFast for secure online payments.

The checkout flow calculates:
- Food subtotal
- Delivery distance
- Delivery fee
- AirXpress platform fee
- Final order total

The customer is then redirected to PayFast for payment and returned to AirXpress Eats after successful payment.

### Staff Dashboard
Staff can:
- View customer orders
- Manage active orders
- Assign drivers
- Update order status
- View order history

### Driver Dashboard
Drivers can:
- Log in
- View delivery requests
- Accept deliveries
- Decline deliveries
- Pick up orders
- Deliver orders
- Complete deliveries

### Management
Management functionality includes:
- Monitor connected businesses
- Monitor completed orders
- Track platform fees
- Manage driver payouts
- View reports
- Manage business subscriptions

## Technology

- Python
- Django 6.1.1
- HTML
- CSS
- JavaScript
- SQLite for local development
- PostgreSQL for production
- Mapbox
- PayFast
- WhiteNoise
- Gunicorn
- Railway

## Local Development

Create and activate a virtual environment if needed:

    python -m venv .venv
    .venv\Scripts\Activate.ps1

Install dependencies:

    pip install -r requirements.txt

Run migrations:

    python manage.py migrate

Start the development server:

    python manage.py runserver

The application will normally be available at:

    http://127.0.0.1:8000/

## Environment Variables

Sensitive credentials should not be committed to GitHub.

Typical configuration includes:

    MAPBOX_TOKEN=
    PAYFAST_MERCHANT_ID=
    PAYFAST_MERCHANT_KEY=
    PAYFAST_PASSPHRASE=
    PAYFAST_SANDBOX=

## Testing

Before committing changes, run:

    python manage.py check

The project should return:

    System check identified no issues (0 silenced).

## Developed By

EdVance Tech (Pty) Ltd.

## Project Status

AirXpress Eats is actively under development.

Current working functionality includes customer ordering, cart management, checkout, returning-customer memory, Mapbox address autocomplete, address verification, distance-based delivery pricing, driver functionality, PayFast Sandbox payments, staff order management and multi-business support.
