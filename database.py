import os
from pathlib import Path

import psycopg2


DATABASE_URL = os.getenv("DATABASE_URL")


class Database:
    def __init__(self, database_url=None):
        self.database_url = database_url or DATABASE_URL

        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL environment variable is not set."
            )

    def connect(self):
        return psycopg2.connect(
            self.database_url,
            sslmode="require",
        )

    def execute(
        self,
        sql,
        params=None,
        fetch=False,
    ):
        connection = self.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    params or (),
                )

                if fetch:
                    result = cursor.fetchall()
                else:
                    result = None

            connection.commit()

            return result

        finally:
            connection.close()

    def initialize_schema(
        self,
        schema_path="schema.sql",
    ):
        path = Path(schema_path)

        if not path.exists():
            raise FileNotFoundError(
                f"Schema file not found: {schema_path}"
            )

        sql = path.read_text(
            encoding="utf-8"
        )

        connection = self.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)

            connection.commit()

        finally:
            connection.close()

        return True


def get_database():
    return Database()
