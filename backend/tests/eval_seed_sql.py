"""仅计数本次请求的业务DML，不记录SQL参数、凭据或用户内容。"""

import re

from eval_seed_state import MODELS

BUSINESS_TABLES = {model.__tablename__ for model in MODELS}
DML = re.compile(
    r'\s*(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:public\.)?"?([a-z_]+)', re.IGNORECASE
)


def observer(records):
    def capture(connection, cursor, statement, parameters, context, executemany):
        matched = DML.match(statement)
        if matched and matched[2].lower() in BUSINESS_TABLES:
            records.append(
                {
                    "table": matched[2].lower(),
                    "operation": matched[1].split()[0].upper(),
                    "rowcount": cursor.rowcount,
                }
            )

    return capture
