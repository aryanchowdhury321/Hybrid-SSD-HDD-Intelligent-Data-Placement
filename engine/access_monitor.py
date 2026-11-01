from datetime import datetime

from database import get_connection


def record_access(block_id, operation):
    operation = operation.upper()
    if operation not in {"READ", "WRITE"}:
        return False, "Invalid operation. Use READ or WRITE."

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT status FROM blocks WHERE block_id = ?",
            (block_id,),
        )
        block = cursor.fetchone()
        if block is None:
            return False, "Block not found."
        if block[0] != "ACTIVE":
            return False, "Block is not active."

        if operation == "READ":
            cursor.execute(
                """
                UPDATE blocks
                SET access_count = access_count + 1,
                    read_count = read_count + 1,
                    last_access_time = ?
                WHERE block_id = ?
                """,
                (timestamp, block_id),
            )
        else:
            cursor.execute(
                """
                UPDATE blocks
                SET access_count = access_count + 1,
                    write_count = write_count + 1,
                    last_access_time = ?
                WHERE block_id = ?
                """,
                (timestamp, block_id),
            )

        cursor.execute(
            """
            INSERT INTO access_history (block_id, operation, timestamp)
            VALUES (?, ?, ?)
            """,
            (block_id, operation, timestamp),
        )
        connection.commit()
        return True, "Access recorded successfully."
    except Exception as error:
        connection.rollback()
        return False, f"Access recording failed: {error}"
    finally:
        connection.close()
