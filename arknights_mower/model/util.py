def from_old_str_to_list(value: list[str] | str) -> list[str]:
    if isinstance(value, str):
        return value.replace("，", ",").split(",")
    return value
