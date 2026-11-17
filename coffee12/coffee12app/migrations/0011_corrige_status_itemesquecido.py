from django.db import migrations


def corrigir_status(apps, schema_editor):
    """Versões antigas gravavam 'achado'/'nao_achado', que não existem nas choices."""
    ItemEsquecido = apps.get_model('coffee12app', 'ItemEsquecido')
    ItemEsquecido.objects.filter(status='achado').update(status='AC')
    ItemEsquecido.objects.filter(status='nao_achado').update(status='NE')


class Migration(migrations.Migration):

    dependencies = [
        ('coffee12app', '0010_preco_promocional_opcional'),
    ]

    operations = [
        migrations.RunPython(corrigir_status, migrations.RunPython.noop),
    ]
