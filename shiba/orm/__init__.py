"""ORM tipado para Shiba.

Uso mínimo:

.. code-block:: python

    import shiba
    from shiba.orm import Model, fields

    class User(Model):
        __table__ = "users"

        id: int = fields.PrimaryKey()
        name: str
        email: str = fields.String(unique=True)
        age: int | None = None

    shiba.set_default_connection(cx)

    User.create_table()
    user = User(name="John", email="j@x.com", age=30)
    user.save()
    User.find(1)
    User.where("age", ">", 18).get()
"""
from shiba.orm import fields
from shiba.orm.model import (
    Model,
    ModelQuery,
    get_default_connection,
    set_default_connection,
)

__all__ = [
    "Model",
    "ModelQuery",
    "fields",
    "get_default_connection",
    "set_default_connection",
]
