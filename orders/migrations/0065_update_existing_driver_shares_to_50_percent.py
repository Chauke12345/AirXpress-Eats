
from decimal import Decimal

from django.db import migrations


def update_driver_shares(apps, schema_editor):
    DeliveryPricing = apps.get_model("orders", "DeliveryPricing")
    database = schema_editor.connection.alias

    DeliveryPricing.objects.using(database).filter(
        driver_percentage=Decimal("40.00")
    ).update(
        driver_percentage=Decimal("50.00")
    )


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0064_alter_deliverypricing_driver_percentage"),
    ]

    operations = [
        migrations.RunPython(
            update_driver_shares,
            migrations.RunPython.noop,
        ),
    ]
