def search_patterns(query: str) -> list[str]:
    def escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    terms = [f"%{escape(query)}%"]
    compact = "".join(query.split())
    if compact.isalpha() and 3 <= len(compact) <= 12:
        chars = [escape(char) for char in compact]
        terms.append("%" + "%".join(chars) + "%")
        if len(chars) >= 4:
            terms.extend(
                "%" + "".join(chars[:i]) + "_" + "".join(chars[i + 1 :]) + "%"
                for i in range(len(chars))
            )
    return terms
