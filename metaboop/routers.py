"""
Database router for metaboop app.

Routes all metaboop models to the 'metaboop' database.
"""


class MetaboopRouter:
    """Route metaboop models to the metaboop database."""

    app_label = 'metaboop'

    def db_for_read(self, model, **hints):
        if model._meta.app_label == self.app_label:
            return 'metaboop'
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == self.app_label:
            return 'metaboop'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations within metaboop or within default
        if (
            obj1._meta.app_label == self.app_label
            or obj2._meta.app_label == self.app_label
        ):
            return obj1._meta.app_label == obj2._meta.app_label
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == self.app_label:
            return db == 'metaboop'
        if db == 'metaboop':
            return False
        return None
