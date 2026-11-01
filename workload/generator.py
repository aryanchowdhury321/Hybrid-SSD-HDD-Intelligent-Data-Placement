import random


def generate_workload(block_ids, number_of_requests=20):
    if not block_ids:
        return []

    workload = []

    for _ in range(number_of_requests):
        block_id = random.choice(block_ids)

        operation = random.choices(
            ["READ", "WRITE"],
            weights=[80, 20],
            k=1
        )[0]

        workload.append({
            "block_id": block_id,
            "operation": operation
        })

    return workload


def generate_hot_workload(block_id, number_of_requests=30):
    workload = []

    for _ in range(number_of_requests):
        operation = random.choices(
            ["READ", "WRITE"],
            weights=[85, 15],
            k=1
        )[0]

        workload.append({
            "block_id": block_id,
            "operation": operation
        })

    return workload