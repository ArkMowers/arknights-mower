"""用标准库 csv 替代 pandas 的 CSV 读写（项目仅用到这些场景）。

替换 pandas 的原因：pandas 在打包产物里占约 5.4MB，而这里只用到了
read_csv / DataFrame.to_csv / iloc 迭代 / to_dict 等少量 CSV 能力。
"""

import csv
import math
import os


# 逐字复刻 pandas.read_csv 的默认行为：
# - 第一行作为表头（生成列名）
# - 后续行返回 row 列表
# - 空文件/无数据时抛 EmptyDataError（对应 pd.errors.EmptyDataError）
class EmptyDataError(Exception):
    pass


def read_csv_rows(path, encoding="utf-8", header="infer"):
    """读 CSV 为行列表。

    header="infer"（默认）时返回 (列名列表, [数据行...])，首行作表头；
    header=False 时返回 [数据行...]（首行也是数据）。
    空文件或只有表头无数据时抛 EmptyDataError，与 pandas 行为一致。
    """
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.reader(f)
        rows = [row for row in reader if row]
    if header == "infer":
        header = True
    if header:
        if not rows:
            raise EmptyDataError
        col_names = rows[0]
        data_rows = rows[1:]
    else:
        col_names = None
        data_rows = rows
    if not data_rows:
        raise EmptyDataError
    if header:
        return col_names, data_rows
    return data_rows


def append_dict_rows(path, rows, fieldnames=None, header=True, encoding="utf-8"):
    """追加写入 dict 行（等价 DataFrame.to_csv(mode='a')）。

    rows: 单行 dict 或 dict 列表，key 即列名。
    header: 文件不存在且为 True 时写表头行。
    """
    if isinstance(rows, dict):
        rows = [rows]
    if fieldnames is None:
        fieldnames = []
        seen = set()
        for r in rows:
            for k in r:
                if k not in seen:
                    seen.add(k)
                    fieldnames.append(k)
    write_header = header and (not os.path.exists(path) or os.path.getsize(path) == 0)
    with open(path, "a", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for r in rows:
            writer.writerow(r)


def append_dated_row(path, date, row, header=True, encoding="utf-8"):
    """追加一条以日期为首列的 CSV 行。

    report/skland 报表共用：日期写入首列（列名为空串，与 pandas 的
    index 列行为一致），后续为数据列。header 仅首次创建时生效。
    """
    data = {"": date, **row}
    append_dict_rows(
        path,
        data,
        fieldnames=["", *[k for k in data if k != ""]],
        header=header,
        encoding=encoding,
    )


def parse_cell_num(value):
    """把 CSV 读出的字符串安全转数值。

    空串/空白/无法解析或非有限的值返回 None（对应 pandas 的 NaN），
    避免 getReportData 等场景 int('') 抛 ValueError 导致接口 500。
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        try:
            number = float(s)
            return number if math.isfinite(number) else None
        except ValueError:
            return None


def read_dicts(path, encoding="utf-8"):
    """读 CSV 为 dict 列表（列名来自表头）。

    等价 pd.read_csv(path).to_dict('records')：
    - 空表头列命名为 Unnamed: N（与 pandas 一致）
    - 空文件/只有表头抛 EmptyDataError（与 pandas 一致）
    - 用 csv.reader 按位置读取，避免空/重复表头列名覆盖导致丢列
    """
    if os.path.getsize(path) == 0:
        raise EmptyDataError
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.reader(f)
        try:
            raw_headers = next(reader)
        except StopIteration:
            raise EmptyDataError
        # 空表头命名 Unnamed: N；重复表头使用 .N 后缀，构造位置唯一的列名
        col_names = []
        seen = set()
        for i, name in enumerate(raw_headers):
            if not name:
                name = f"Unnamed: {i}"
            new_name = name
            suffix = 1
            while new_name in seen:
                new_name = f"{name}.{suffix}"
                suffix += 1
            seen.add(new_name)
            col_names.append(new_name)
        rows = []
        for row in reader:
            if not row:
                continue
            r = {
                name: row[i] if i < len(row) else "" for i, name in enumerate(col_names)
            }
            rows.append(r)
        if not rows:
            raise EmptyDataError
        return rows
