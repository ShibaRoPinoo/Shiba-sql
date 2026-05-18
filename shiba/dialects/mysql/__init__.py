"""Dialecto MySQL/MariaDB."""
from shiba.dialects.mysql.dialect import MySQLDialect
from shiba.dialects.mysql.driver import Database

__all__ = ["Database", "MySQLDialect"]
