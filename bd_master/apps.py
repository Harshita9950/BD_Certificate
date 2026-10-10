from django.apps import AppConfig


class BdMasterConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bd_master'
    verbose_name = 'BD Master Configuration'
