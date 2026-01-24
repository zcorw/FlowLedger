import re
from typing import Mapping

_PLACEHOLDER_PATTERN = re.compile(r"\$\{(\w+)\}")

def render_sql_template(template: str, params: Mapping[str, str]) -> str:
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        if key not in params:
            raise KeyError(f"Missing SQL template parameter: {key}")
        return params[key]

    return _PLACEHOLDER_PATTERN.sub(replacer, template)

def get_exchange_rate_by_as_of(*, code: str, as_of: str, column: str, currency: str, as_of_column: str = "as_of") -> str:
    sql_template = """
    CASE
      WHEN ${currency_alias}.currency = ${target_code} THEN 1::numeric
      ELSE COALESCE(
        (
          SELECT er.rate
          FROM currency.exchange_rates er
          WHERE er.base_code = ${currency_alias}.currency
            AND er.quote_code = ${target_code}
            AND er.rate_date <= ${as_of_alias}.${as_of_column}::date
          ORDER BY er.rate_date DESC
          LIMIT 1
        ),
        (
          SELECT 1 / er2.rate
          FROM currency.exchange_rates er2
          WHERE er2.base_code = ${target_code}
            AND er2.quote_code = ${currency_alias}.currency
            AND er2.rate_date <= ${as_of_alias}.${as_of_column}::date
          ORDER BY er2.rate_date DESC
          LIMIT 1
        )
      )
    END AS ${column_alias}
    """
    params = {
        "target_code": code,
        "as_of_alias": as_of,
        "column_alias": column,
        "currency_alias": currency,
        "as_of_column": as_of_column
    }
    return render_sql_template(sql_template, params)