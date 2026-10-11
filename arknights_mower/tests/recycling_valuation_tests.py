"""Offline import, persistence and valuation consistency through report APIs."""

from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from arknights_mower.data import key_mapping
from arknights_mower.solvers import record
from arknights_mower.tests.recycling_collection_tests import at, workbook_rows
from arknights_mower.tests.recycling_collection_tests import db as db
from arknights_mower.utils.recycling_valuation import (
    DEFAULT_RATIOS,
    default_valuation,
    import_yituliu_values,
    validate_ratios,
)


def value_file(
    *,
    omit=None,
    price="10",
    duplicate=False,
    formula=False,
    mismatch=False,
    shared=False,
    only_new=False,
    optional_unpriced=False,
    lmd_price="0.01",
):
    from arknights_mower.utils.recycling import recycling_model

    model = recycling_model()
    names = sorted({row["name"] for row in model["ordinary"] + model["extra"]})
    rows = [("物品id", "物品名称", "等效理智", "物品稀有度")]
    for name in names:
        if name != omit:
            rows.append(
                (
                    str(key_mapping[name][0]),
                    name + ("错误" if mismatch else ""),
                    price,
                    "2",
                )
            )
    rows.append(("4001", "龙门币", lmd_price, "1"))
    if optional_unpriced:
        rows.append(("future_unpriced", "未定价新物品", "Infinity", "3"))
    if duplicate:
        rows.append((str(key_mapping[names[0]][0]), names[0], "11", "2"))
    if only_new:
        rows = [rows[0], ("future_999", "未来新材料", price, "3")]
    strings = []
    xml_rows = []
    for index, values in enumerate(rows, 1):
        cells = []
        for column, value in enumerate(values):
            address = f"{chr(65 + column)}{index}"
            f = "<f>1+1</f>" if formula and index == 2 and column == 2 else ""
            if shared:
                strings.append(value)
                cells.append(f'<c r="{address}" t="s">{f}<v>{len(strings) - 1}</v></c>')
            else:
                cells.append(
                    f'<c r="{address}" t="inlineStr">{f}<is><t>{escape(value)}</t></is></c>'
                )
        xml_rows.append(f'<row r="{index}">{"".join(cells)}</row>')
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="物品价值表" sheetId="7" r:id="rId7"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="rId7" Target="/xl/worksheets/sheet7.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/worksheets/sheet7.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + "".join(xml_rows)
            + "</sheetData></worksheet>",
        )
        if shared:
            archive.writestr(
                "xl/sharedStrings.xml",
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                + "".join(f"<si><t>{escape(s)}</t></si>" for s in strings)
                + "</sst>",
            )
    return output.getvalue()


@pytest.mark.parametrize("shared", [True, False])
def test_imports_complete_yituliu_table_with_workbook_relationships(shared):
    values = import_yituliu_values(value_file(shared=shared))
    assert len(values["prices"]) == 50
    assert values["prices"]["装置"] == 10
    assert values["lmd_sanity"] == 0.01


def test_optional_unpriced_rows_preserve_existing_values(db):
    imported = import_yituliu_values(value_file(optional_unpriced=True))
    saved = record.update_recycling_valuation(imported=imported)
    assert saved["last_import"]["unpriced"] == ["未定价新物品"]
    assert "未定价新物品" not in saved["prices"]
    assert saved["prices"]["装置"] == 10


@pytest.mark.parametrize(
    "options",
    [
        {"price": "-1"},
        {"price": "nan"},
        {"price": "inf"},
        {"price": "not a number"},
        {"duplicate": True},
        {"formula": True},
        {"mismatch": True},
        {"lmd_price": "0"},
        {"lmd_price": "1e-12"},
    ],
)
def test_invalid_import_is_rejected(options):
    with pytest.raises(ValueError):
        import_yituliu_values(value_file(**options))


@pytest.mark.parametrize("content", [b"", b"not xlsx", b"x" * (2 * 1024 * 1024 + 1)])
def test_import_rejects_invalid_or_oversized_archive(content):
    with pytest.raises(ValueError):
        import_yituliu_values(content)


@pytest.mark.parametrize(
    "key,value",
    [
        ("experience", 0),
        ("experience", 0.00000001),
        ("gold", -1),
        ("order", float("nan")),
        ("order", True),
        ("efficiency", None),
        ("efficiency", 1001),
    ],
)
def test_invalid_ratio_rejected_without_changing_saved_values(db, key, value):
    original = record.get_recycling_valuation()
    with pytest.raises(ValueError):
        record.update_recycling_valuation(ratios={**DEFAULT_RATIOS, key: value})
    assert record.get_recycling_valuation() == original


def test_ratios_require_complete_input():
    for value in [None, [], {}, {"experience": 1}, {**DEFAULT_RATIOS, "other": 1}]:
        with pytest.raises(ValueError):
            validate_ratios(value)


def test_saved_import_revalues_history_and_export_using_same_snapshot(db):
    record.save_recycling_collection("event", at(10), ["旅骨"], {"装置": 2})
    ratios = {"experience": 2, "gold": 0.4, "order": 0.6, "efficiency": 1.5}
    record.update_recycling_valuation(ratios=ratios)
    saved = record.update_recycling_valuation(
        imported=import_yituliu_values(value_file())
    )
    assert saved["ratios"] == ratios
    assert saved["imported_at"] > 0
    report = record.get_recycling_history("2026-10-10", "2026-10-10")
    result = report["comparison"]
    assert result["actual_sanity"] == pytest.approx(20)
    assert result["expected_sanity"] == pytest.approx(20)
    assert result["calculator"]["daily_sanity"] == pytest.approx(5.263065)
    assert result["calculator"]["configured_daily_sanity"] == pytest.approx(7.8945975)
    assert result["calculator"]["manufacturing_equivalent"] == pytest.approx(
        0.049341234375
    )
    with record.export_recycling_history("2026-10-10", "2026-10-10") as workbook:
        _, _, overview = workbook_rows(workbook, 1)
        values = {row[0]: row[1] for row in overview[1:]}
        assert float(values["总理智收益"]) == 20
        assert float(values["理论期望收益"]) == 20
        _, _, inputs = workbook_rows(workbook, 5)
        values = {row[0]: row[1] for row in inputs[1:]}
        assert values["装置"] == "10.0"
        assert values["经验书价值比例"] == "2"
        assert values["价值来源"] == "一图流导入（未提供的价值保留原值）"
    record.update_recycling_valuation(ratios={**ratios, "gold": 2})
    changed = record.get_recycling_history("2026-10-10", "2026-10-10")
    assert changed["records"] == report["records"]
    assert changed["comparison"]["actual_sanity"] == 20
    assert (
        changed["comparison"]["calculator"]["manufacturing_equivalent"]
        > result["calculator"]["manufacturing_equivalent"]
    )
    record.update_recycling_valuation(reset=True)
    assert record.get_recycling_valuation() == {
        **default_valuation(),
        "base_algorithm_saved": True,
    }
    assert (
        record.get_recycling_history("2026-10-10", "2026-10-10")["records"]
        == report["records"]
    )


def test_import_and_settings_routes_preserve_previous_snapshot_on_errors(
    db, monkeypatch
):
    import server

    monkeypatch.setattr(server.app, "token", "valuation-test", raising=False)
    client = server.app.test_client()
    route = "/report/recycling_settings"
    headers = {"token": "valuation-test"}
    for method, path in [
        ("GET", route),
        ("PUT", route),
        ("DELETE", route),
        ("POST", route + "/import"),
    ]:
        assert client.open(path, method=method).status_code == 403
    assert (
        client.put(
            route, headers=headers, json={"ratios": {**DEFAULT_RATIOS, "order": 0.5}}
        ).status_code
        == 200
    )
    response = client.post(
        route + "/import",
        headers=headers,
        data={"file": (BytesIO(value_file()), "values.xlsx")},
    )
    assert response.status_code == 200
    before = client.get(route, headers=headers).json
    assert before["ratios"]["order"] == 0.5
    for content, name in [
        (value_file(formula=True), "values.xlsx"),
        (b"bad", "values.xlsx"),
        (value_file(), "values.csv"),
    ]:
        response = client.post(
            route + "/import", headers=headers, data={"file": (BytesIO(content), name)}
        )
        assert response.status_code == 400
        assert client.get(route, headers=headers).json == before
    for payload in [{}, {"ratios": None}, {"ratios": {"experience": 1}}]:
        assert client.put(route, headers=headers, json=payload).status_code == 400
        assert client.get(route, headers=headers).json == before
    assert client.delete(route, headers=headers).json == {
        **default_valuation(),
        "base_algorithm_saved": True,
    }


def test_incremental_import_keeps_new_materials_and_previous_prices(db):
    original = record.get_recycling_valuation()
    imported = import_yituliu_values(value_file(only_new=True, price="20"))
    saved = record.update_recycling_valuation(imported=imported)
    assert saved["prices"]["未来新材料"] == 20
    assert saved["item_ids"]["未来新材料"] == "future_999"
    assert saved["prices"]["装置"] == original["prices"]["装置"]
    assert saved["lmd_sanity"] == original["lmd_sanity"]
    assert saved["last_import"] == {
        "updated": 1,
        "added": 1,
        "retained": len(original["prices"]),
        "unpriced": [],
    }
    record.save_recycling_collection("new", at(10), [], {"未来新材料": 3})
    stats = record.get_recycling_history("2026-10-10", "2026-10-10")["comparison"]
    assert stats["actual_sanity"] == 60
    assert stats["expected_sanity"] is None
    assert stats["difference"] is None
    assert stats["unmodeled_materials"] == ["未来新材料"]
    assert stats["unknown_materials"] == []
    record.update_recycling_valuation(
        imported=import_yituliu_values(value_file(only_new=True, price="30"))
    )
    assert (
        record.get_recycling_history("2026-10-10", "2026-10-10")["comparison"][
            "actual_sanity"
        ]
        == 90
    )
    assert record.get_recycling_valuation()["last_import"]["added"] == 0
    record.update_recycling_valuation(
        imported=import_yituliu_values(value_file(omit="装置"))
    )
    assert (
        record.get_recycling_valuation()["prices"]["装置"] == original["prices"]["装置"]
    )
    assert record.get_recycling_valuation()["prices"]["未来新材料"] == 30


def test_new_material_identity_conflict_leaves_saved_prices_unchanged(db):
    imported = import_yituliu_values(value_file(only_new=True))
    before = record.update_recycling_valuation(imported=imported)
    conflicting = import_yituliu_values(value_file(only_new=True))
    conflicting["item_ids"]["未来新材料"] = "another_id"
    with pytest.raises(ValueError, match="已保存 ID"):
        record.update_recycling_valuation(imported=conflicting)
    assert record.get_recycling_valuation() == before


@pytest.mark.parametrize("algorithm", [0, 1, 2, -1])
def test_shared_base_algorithm_persists_and_rejects_mismatched_preset(db, algorithm):
    from arknights_mower.utils.recycling_valuation import BASE_ALGORITHMS

    ratios = {**DEFAULT_RATIOS, **BASE_ALGORITHMS.get(algorithm, {"gold": 2})}
    saved = record.update_recycling_valuation(ratios=ratios, base_algorithm=algorithm)
    assert record.get_recycling_valuation() == saved
    assert saved["base_algorithm"] == algorithm
    assert saved["base_algorithm_saved"] is True
    with pytest.raises(ValueError, match="不一致"):
        record.update_recycling_valuation(
            ratios={**ratios, "gold": 9}, base_algorithm=0
        )
    assert record.get_recycling_valuation() == saved


def test_imported_values_reach_growth_and_recycling_with_same_source(db):
    from arknights_mower.utils.growth_value import consumed_statistics, price_catalog

    record.update_recycling_valuation(
        imported=import_yituliu_values(value_file(only_new=True, price="20"))
    )
    record.save_recycling_collection("future", at(10), [], {"未来新材料": 3})
    catalog = price_catalog()
    assert catalog["items"]["future_999"]["value"] == 20
    char = {"id": "char_test", "evolvePhase": 0, "level": 1, "mainSkillLevel": 2}
    definition = {
        "rarity": 6,
        "phases": [{"max_level": 1}],
        "basic_skills": [[{"id": "future_999", "count": 3}]],
    }
    data = {
        "characters": {"char_test": definition},
        "experience": [],
        "level_gold": [],
        "promotion_gold": [],
    }
    row = consumed_statistics([char], {}, data)["6"]
    comparison = record.get_recycling_history("2026-10-10", "2026-10-10")["comparison"]
    assert row["sanity_value"] == comparison["actual_sanity"] == 60
    assert row["sanity_source"] == comparison["valuation"]["metadata"]
    assert row["sanity_source"]["pricing_mode"] == "imported"
    assert comparison["expected_sanity"] is None


def test_legacy_builtin_prices_upgrade_but_custom_imports_survive(db):
    import json

    with record._conn() as connection:
        connection.execute(
            "INSERT INTO recycling_valuation VALUES (1, ?)",
            (
                json.dumps(
                    {
                        "source": "计算器内置价值快照",
                        "prices": {"装置": 8.159},
                        "item_ids": {"装置": "30062"},
                        "ratios": DEFAULT_RATIOS,
                    }
                ),
            ),
        )
    assert record.get_recycling_valuation()["prices"]["装置"] == pytest.approx(
        8.16879195924877
    )
    with record._conn() as connection:
        connection.execute(
            "UPDATE recycling_valuation SET payload = ?",
            (
                json.dumps(
                    {
                        "source": "一图流导入（未提供的价值保留原值）",
                        "prices": {"装置": 11},
                        "item_ids": {"装置": "30062"},
                        "ratios": DEFAULT_RATIOS,
                        "imported_at": 1,
                    }
                ),
            ),
        )
    saved = record.get_recycling_valuation()
    assert saved["base_algorithm_saved"] is False
    assert saved["prices"]["装置"] == 11
    assert saved["metadata"]["pricing_mode"] == "imported"
    assert saved["metadata"]["source"] == saved["source"]
    assert "中级作战记录" in saved["prices"]


def test_settings_api_preserves_explicit_custom_algorithm(db, monkeypatch):
    import server

    monkeypatch.setattr(server.app, "token", "", raising=False)
    client = server.app.test_client()
    saved = client.put(
        "/report/recycling_settings",
        json={"ratios": DEFAULT_RATIOS, "base_algorithm": -1},
    )
    assert saved.status_code == 200
    assert saved.json["base_algorithm"] == -1
    before = saved.json
    assert (
        client.put(
            "/report/recycling_settings",
            json={"ratios": DEFAULT_RATIOS, "base_algorithm": 2},
        ).status_code
        == 400
    )
    assert client.get("/report/recycling_settings").json == before


def test_default_assumptions_use_ce6_ls6_and_quarter_algorithm(db):
    from arknights_mower.utils.growth_value import price_catalog

    saved = record.get_recycling_valuation()
    assert saved["base_algorithm"] == 1
    assert saved["ratios"] == {
        "experience": 1,
        "gold": 0.8,
        "order": 733 / 2990,
        "efficiency": 1,
    }
    assert saved["metadata"]["pricing_config"]["expCoefficient"] == 0.9568
    assert price_catalog()["items"]["2003"]["value"] == pytest.approx(3.44448)
