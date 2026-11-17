"""
MySQL connection and query helpers.

Every other file talks to the database through these four functions:
    query()      SELECT -> list of rows (dicts)
    query_one()  SELECT -> one row or None
    execute()    INSERT / UPDATE / DELETE -> number of rows changed
    insert()     INSERT -> id of the new row
and calls commit() to save a group of changes together.
"""
from datetime import datetime
from decimal import Decimal

import pymysql
from flask import g

import config


def db():
    """One MySQL connection per web request (stored in Flask's `g`), closed by close_db()."""
    if "db" not in g:
        g.db = pymysql.connect(
            host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER,
            password=config.DB_PASS, database=config.DB_NAME,
            cursorclass=pymysql.cursors.DictCursor, autocommit=False,
            ssl_ca=config.DB_SSL_CA or None,           # encrypted connection for cloud MySQL
            connect_timeout=10,
        )
    return g.db


def close_db(_exc=None):
    """Runs after every request. Anything not committed is rolled back when the connection closes."""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def commit():
    db().commit()


def clean(row):
    """Make a row JSON-friendly: Decimal -> float, datetime -> 'YYYY-MM-DD HH:MM:SS'."""
    if row is None:
        return None
    out = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            value = float(value)
        elif isinstance(value, datetime):
            value = value.strftime("%Y-%m-%d %H:%M:%S")
        out[key] = value
    return out


def query(sql, args=()):
    with db().cursor() as cur:
        cur.execute(sql, args)
        return [clean(r) for r in cur.fetchall()]


def query_one(sql, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql, args=()):
    with db().cursor() as cur:
        return cur.execute(sql, args)


def insert(sql, args=()):
    with db().cursor() as cur:
        cur.execute(sql, args)
        return cur.lastrowid
